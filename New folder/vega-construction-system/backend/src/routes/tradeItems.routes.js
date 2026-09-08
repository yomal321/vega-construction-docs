import { Router } from 'express';
import { pool } from '../config/db.js';
import { requireAuth } from '../middleware/auth.js';
import { requireRole } from '../middleware/roles.js';
import { writeAudit } from '../utils/audit.js';
import { resolveTradeItemRate, FLOOR_ORDER } from '../utils/rateEngine.js';

const router = Router();
router.use(requireAuth);

// GET /api/trade-items?search=
router.get('/', async (req, res) => {
  const { search } = req.query;
  const params = [];
  let where = '';
  if (search) {
    params.push(`%${search}%`);
    where = `WHERE description ILIKE $1 OR code ILIKE $1`;
  }
  const { rows } = await pool.query(
    `SELECT * FROM trade_items ${where} ORDER BY code NULLS LAST, description`,
    params
  );
  res.json(rows);
});

// GET /api/trade-items/:id — includes recipe (components) and resolved rate
router.get('/:id', async (req, res) => {
  const { id } = req.params;
  const floor = FLOOR_ORDER.includes(req.query.floor) ? req.query.floor : 'ground';

  const { rows: itemRows } = await pool.query('SELECT * FROM trade_items WHERE id = $1', [id]);
  if (!itemRows[0]) return res.status(404).json({ error: 'Trade item not found.' });

  try {
    const resolved = await resolveTradeItemRate(Number(id), floor);
    res.json({ ...itemRows[0], resolved });
  } catch (err) {
    res.status(422).json({ error: err.message });
  }
});

// GET /api/trade-items/:id/rate?floor=first — just the number, for quick lookups (e.g. from BSR page)
router.get('/:id/rate', async (req, res) => {
  const floor = FLOOR_ORDER.includes(req.query.floor) ? req.query.floor : 'ground';
  try {
    const resolved = await resolveTradeItemRate(Number(req.params.id), floor);
    res.json(resolved);
  } catch (err) {
    res.status(422).json({ error: err.message });
  }
});

// POST /api/trade-items — create the shell item (recipe added separately)
router.post('/', requireRole('admin', 'estimator'), async (req, res) => {
  const { code, description, unit, analysis_qty } = req.body;
  if (!description || !unit) {
    return res.status(400).json({ error: 'description and unit are required.' });
  }
  const { rows } = await pool.query(
    `INSERT INTO trade_items (code, description, unit, analysis_qty, updated_by)
     VALUES ($1, $2, $3, $4, $5) RETURNING *`,
    [code || null, description, unit, analysis_qty || 1, req.user.id]
  );
  await writeAudit({ tableName: 'trade_items', recordId: rows[0].id, action: 'create', changedBy: req.user.id, newValue: rows[0] });
  res.status(201).json(rows[0]);
});

router.put('/:id', requireRole('admin', 'estimator'), async (req, res) => {
  const { id } = req.params;
  const { description, unit, analysis_qty, code } = req.body;

  const { rows: existingRows } = await pool.query('SELECT * FROM trade_items WHERE id = $1', [id]);
  if (!existingRows[0]) return res.status(404).json({ error: 'Trade item not found.' });

  const { rows } = await pool.query(
    `UPDATE trade_items
     SET description = COALESCE($1, description),
         unit = COALESCE($2, unit),
         analysis_qty = COALESCE($3, analysis_qty),
         code = COALESCE($4, code),
         updated_at = now(),
         updated_by = $5
     WHERE id = $6 RETURNING *`,
    [description, unit, analysis_qty, code, req.user.id, id]
  );

  await writeAudit({ tableName: 'trade_items', recordId: id, action: 'update', changedBy: req.user.id, oldValue: existingRows[0], newValue: rows[0] });
  res.json(rows[0]);
});

// POST /api/trade-items/:id/components — replace the full recipe in one call
// body: { components: [{ component_kind, base_item_id?, child_trade_item_id?, quantity, note? }] }
router.post('/:id/components', requireRole('admin', 'estimator'), async (req, res) => {
  const { id } = req.params;
  const { components } = req.body;
  if (!Array.isArray(components)) {
    return res.status(400).json({ error: 'components must be an array.' });
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await client.query('DELETE FROM trade_item_components WHERE trade_item_id = $1', [id]);

    for (const c of components) {
      if (c.child_trade_item_id && Number(c.child_trade_item_id) === Number(id)) {
        throw new Error('A trade item cannot reference itself in its own recipe.');
      }
      await client.query(
        `INSERT INTO trade_item_components
           (trade_item_id, component_kind, base_item_id, child_trade_item_id, quantity, note)
         VALUES ($1, $2, $3, $4, $5, $6)`,
        [id, c.component_kind, c.base_item_id || null, c.child_trade_item_id || null, c.quantity, c.note || null]
      );
    }
    await client.query('COMMIT');
  } catch (err) {
    await client.query('ROLLBACK');
    return res.status(422).json({ error: err.message });
  } finally {
    client.release();
  }

  const resolved = await resolveTradeItemRate(Number(id));
  res.json({ ok: true, resolved });
});

// PUT /api/trade-items/:id/floor-rates — set per-floor multipliers
// body: { rates: [{ floor: 'first', multiplier: 1.1 }, ...] }
router.put('/:id/floor-rates', requireRole('admin', 'estimator'), async (req, res) => {
  const { id } = req.params;
  const { rates } = req.body;
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    for (const r of rates) {
      await client.query(
        `INSERT INTO trade_item_floor_rates (trade_item_id, floor, multiplier)
         VALUES ($1, $2, $3)
         ON CONFLICT (trade_item_id, floor) DO UPDATE SET multiplier = EXCLUDED.multiplier`,
        [id, r.floor, r.multiplier]
      );
    }
    await client.query('COMMIT');
  } catch (err) {
    await client.query('ROLLBACK');
    return res.status(422).json({ error: err.message });
  } finally {
    client.release();
  }
  res.json({ ok: true });
});

export default router;
