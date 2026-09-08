import { Router } from 'express';
import { pool } from '../config/db.js';
import { requireAuth } from '../middleware/auth.js';
import { requireRole } from '../middleware/roles.js';

const router = Router();
router.use(requireAuth);

const CATEGORIES = ['labour', 'material', 'sub_contractor', 'machinery', 'transport', 'other'];

// GET /api/projects/:projectId/expenses?category=&stage_id=
router.get('/projects/:projectId/expenses', async (req, res) => {
  const { projectId } = req.params;
  const { category, stage_id } = req.query;

  const conditions = ['e.project_id = $1'];
  const params = [projectId];
  if (category) {
    params.push(category);
    conditions.push(`e.category = $${params.length}`);
  }
  if (stage_id) {
    params.push(stage_id);
    conditions.push(`e.project_stage_id = $${params.length}`);
  }

  const { rows } = await pool.query(
    `SELECT e.*, ps.name AS stage_name, ti.description AS trade_item_description, u.name AS created_by_name
     FROM expenses e
     LEFT JOIN project_stages ps ON ps.id = e.project_stage_id
     LEFT JOIN trade_items ti ON ti.id = e.trade_item_id
     LEFT JOIN users u ON u.id = e.created_by
     WHERE ${conditions.join(' AND ')}
     ORDER BY e.expense_date DESC, e.id DESC`,
    params
  );
  res.json(rows);
});

// POST /api/projects/:projectId/expenses
router.post('/projects/:projectId/expenses', requireRole('admin', 'accounts'), async (req, res) => {
  const { projectId } = req.params;
  const {
    vendor_name, category, invoice_ref, amount,
    expense_date, payment_method, notes,
    project_stage_id, trade_item_id,
  } = req.body;

  if (!vendor_name || !category || !amount) {
    return res.status(400).json({ error: 'vendor_name, category and amount are required.' });
  }
  if (!CATEGORIES.includes(category)) {
    return res.status(400).json({ error: `category must be one of: ${CATEGORIES.join(', ')}` });
  }

  const { rows } = await pool.query(
    `INSERT INTO expenses
       (project_id, project_stage_id, trade_item_id, vendor_name, category,
        invoice_ref, amount, expense_date, payment_method, notes, created_by)
     VALUES ($1,$2,$3,$4,$5,$6,$7,COALESCE($8, CURRENT_DATE),$9,$10,$11)
     RETURNING *`,
    [projectId, project_stage_id || null, trade_item_id || null, vendor_name, category,
     invoice_ref || null, amount, expense_date || null, payment_method || null, notes || null, req.user.id]
  );

  res.status(201).json(rows[0]);
});

router.delete('/expenses/:id', requireRole('admin', 'accounts'), async (req, res) => {
  const { rowCount } = await pool.query('DELETE FROM expenses WHERE id = $1', [req.params.id]);
  if (!rowCount) return res.status(404).json({ error: 'Expense not found.' });
  res.status(204).send();
});

export default router;
