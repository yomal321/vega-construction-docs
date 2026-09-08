import { Router } from 'express';
import { pool } from '../config/db.js';
import { requireAuth } from '../middleware/auth.js';
import { requireRole } from '../middleware/roles.js';
import { resolveTradeItemRate, FLOOR_ORDER } from '../utils/rateEngine.js';

const router = Router();
router.use(requireAuth);

// GET /api/projects/:projectId/bsr — creates the BSR on first access if it doesn't exist yet
router.get('/projects/:projectId/bsr', async (req, res) => {
  const { projectId } = req.params;

  let { rows } = await pool.query('SELECT * FROM bsr WHERE project_id = $1', [projectId]);
  let bsr = rows[0];
  if (!bsr) {
    ({ rows } = await pool.query(
      `INSERT INTO bsr (project_id) VALUES ($1) RETURNING *`,
      [projectId]
    ));
    bsr = rows[0];
  }

  const { rows: lineItems } = await pool.query(
    `SELECT bli.*, ti.description, ti.unit, ti.code
     FROM bsr_line_items bli
     JOIN trade_items ti ON ti.id = bli.trade_item_id
     WHERE bli.bsr_id = $1
     ORDER BY bli.added_at`,
    [bsr.id]
  );

  const grandTotal = lineItems.reduce((sum, li) => sum + Number(li.line_total), 0);
  res.json({ ...bsr, lineItems, grandTotal });
});

// POST /api/projects/:projectId/bsr/items — add a trade item to the BSR
// The rate is resolved server-side and snapshotted, so later price changes
// don't silently alter a BSR that's already been quoted to the client.
router.post('/projects/:projectId/bsr/items', requireRole('admin', 'estimator'), async (req, res) => {
  const { projectId } = req.params;
  const { trade_item_id, quantity, floor } = req.body;

  if (!trade_item_id || !quantity) {
    return res.status(400).json({ error: 'trade_item_id and quantity are required.' });
  }
  const resolvedFloor = FLOOR_ORDER.includes(floor) ? floor : 'ground';

  let bsrId;
  const { rows: bsrRows } = await pool.query('SELECT id FROM bsr WHERE project_id = $1', [projectId]);
  if (bsrRows[0]) {
    bsrId = bsrRows[0].id;
  } else {
    const { rows } = await pool.query('INSERT INTO bsr (project_id) VALUES ($1) RETURNING id', [projectId]);
    bsrId = rows[0].id;
  }

  let resolved;
  try {
    resolved = await resolveTradeItemRate(Number(trade_item_id), resolvedFloor);
  } catch (err) {
    return res.status(422).json({ error: err.message });
  }

  const { rows } = await pool.query(
    `INSERT INTO bsr_line_items (bsr_id, trade_item_id, floor, quantity, rate_snapshot, added_by)
     VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
    [bsrId, trade_item_id, resolvedFloor, quantity, resolved.rate, req.user.id]
  );

  res.status(201).json(rows[0]);
});

router.delete('/bsr-items/:id', requireRole('admin', 'estimator'), async (req, res) => {
  const { id } = req.params;
  const { rowCount } = await pool.query('DELETE FROM bsr_line_items WHERE id = $1', [id]);
  if (!rowCount) return res.status(404).json({ error: 'Line item not found.' });
  res.status(204).send();
});

export default router;
