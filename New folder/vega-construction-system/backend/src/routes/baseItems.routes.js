import { Router } from 'express';
import { pool } from '../config/db.js';
import { requireAuth } from '../middleware/auth.js';
import { requireRole } from '../middleware/roles.js';
import { writeAudit } from '../utils/audit.js';

const router = Router();
router.use(requireAuth);

// GET /api/base-items?category=material&search=cement
router.get('/', async (req, res) => {
  const { category, search } = req.query;
  const conditions = [];
  const params = [];

  if (category) {
    params.push(category);
    conditions.push(`category = $${params.length}`);
  }
  if (search) {
    params.push(`%${search}%`);
    conditions.push(`(description ILIKE $${params.length} OR code ILIKE $${params.length})`);
  }

  const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
  const { rows } = await pool.query(
    `SELECT bi.*, u.name AS updated_by_name
     FROM base_items bi
     LEFT JOIN users u ON u.id = bi.updated_by
     ${where}
     ORDER BY bi.trade_group, bi.description`,
    params
  );
  res.json(rows);
});

// POST /api/base-items — admin or estimator only
router.post('/', requireRole('admin', 'estimator'), async (req, res) => {
  const { code, category, trade_group, description, unit, unit_price } = req.body;
  if (!category || !description || !unit || unit_price == null) {
    return res.status(400).json({ error: 'category, description, unit and unit_price are required.' });
  }

  const { rows } = await pool.query(
    `INSERT INTO base_items (code, category, trade_group, description, unit, unit_price, updated_by)
     VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *`,
    [code || null, category, trade_group || null, description, unit, unit_price, req.user.id]
  );

  await writeAudit({
    tableName: 'base_items',
    recordId: rows[0].id,
    action: 'create',
    changedBy: req.user.id,
    newValue: rows[0],
  });

  res.status(201).json(rows[0]);
});

// PUT /api/base-items/:id — this is the #1 requirement from the BRD:
// every edit must auto-stamp updated_at/updated_by, and be audit-logged.
router.put('/:id', requireRole('admin', 'estimator'), async (req, res) => {
  const { id } = req.params;
  const { description, unit, unit_price, trade_group, code } = req.body;

  const { rows: existingRows } = await pool.query('SELECT * FROM base_items WHERE id = $1', [id]);
  const existing = existingRows[0];
  if (!existing) return res.status(404).json({ error: 'Item not found.' });

  const { rows } = await pool.query(
    `UPDATE base_items
     SET description = COALESCE($1, description),
         unit = COALESCE($2, unit),
         unit_price = COALESCE($3, unit_price),
         trade_group = COALESCE($4, trade_group),
         code = COALESCE($5, code),
         updated_at = now(),
         updated_by = $6
     WHERE id = $7
     RETURNING *`,
    [description, unit, unit_price, trade_group, code, req.user.id, id]
  );

  await writeAudit({
    tableName: 'base_items',
    recordId: id,
    action: 'update',
    changedBy: req.user.id,
    oldValue: existing,
    newValue: rows[0],
  });

  res.json(rows[0]);
});

// DELETE /api/base-items/:id — admin only (deleting a rate item is destructive)
router.delete('/:id', requireRole('admin'), async (req, res) => {
  const { id } = req.params;
  const { rows: existingRows } = await pool.query('SELECT * FROM base_items WHERE id = $1', [id]);
  if (!existingRows[0]) return res.status(404).json({ error: 'Item not found.' });

  await pool.query('DELETE FROM base_items WHERE id = $1', [id]);
  await writeAudit({
    tableName: 'base_items',
    recordId: id,
    action: 'delete',
    changedBy: req.user.id,
    oldValue: existingRows[0],
  });

  res.status(204).send();
});

export default router;
