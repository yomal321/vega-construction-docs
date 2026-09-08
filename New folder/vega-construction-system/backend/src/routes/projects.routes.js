import { Router } from 'express';
import { pool } from '../config/db.js';
import { requireAuth } from '../middleware/auth.js';
import { requireRole } from '../middleware/roles.js';

const router = Router();
router.use(requireAuth);

const MILESTONES = [
  { milestone: 'advance', percentage: 0.5 },
  { milestone: 'interim', percentage: 0.25 },
  { milestone: 'final', percentage: 0.25 },
];

router.get('/', async (req, res) => {
  const { rows } = await pool.query(
    `SELECT p.*, count(ps.id) AS stage_count_actual
     FROM projects p
     LEFT JOIN project_stages ps ON ps.project_id = p.id
     GROUP BY p.id
     ORDER BY p.created_at DESC`
  );
  res.json(rows);
});

// POST /api/projects — creates the project AND its stages + 3 milestones per stage.
// Stage count is configurable per project (not hardcoded), per confirmed scope.
router.post('/', requireRole('admin', 'estimator'), async (req, res) => {
  const { name, client_name, site_address, stage_count, stage_contract_amounts } = req.body;
  if (!name || !client_name || !stage_count) {
    return res.status(400).json({ error: 'name, client_name and stage_count are required.' });
  }
  if (stage_count < 1) {
    return res.status(400).json({ error: 'stage_count must be at least 1.' });
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    const { rows: projectRows } = await client.query(
      `INSERT INTO projects (name, client_name, site_address, stage_count, created_by)
       VALUES ($1, $2, $3, $4, $5) RETURNING *`,
      [name, client_name, site_address || null, stage_count, req.user.id]
    );
    const project = projectRows[0];

    for (let i = 1; i <= stage_count; i++) {
      const contractAmount = stage_contract_amounts?.[i - 1] ?? 0;
      const { rows: stageRows } = await client.query(
        `INSERT INTO project_stages (project_id, stage_number, name, contract_amount)
         VALUES ($1, $2, $3, $4) RETURNING *`,
        [project.id, i, `Stage ${i}`, contractAmount]
      );
      const stage = stageRows[0];

      for (const m of MILESTONES) {
        await client.query(
          `INSERT INTO stage_payments (project_stage_id, milestone, percentage, amount)
           VALUES ($1, $2, $3, $4)`,
          [stage.id, m.milestone, m.percentage, contractAmount * m.percentage]
        );
      }
    }

    await client.query('COMMIT');
    res.status(201).json(project);
  } catch (err) {
    await client.query('ROLLBACK');
    res.status(500).json({ error: err.message });
  } finally {
    client.release();
  }
});

router.get('/:id', async (req, res) => {
  const { id } = req.params;
  const { rows: projectRows } = await pool.query('SELECT * FROM projects WHERE id = $1', [id]);
  if (!projectRows[0]) return res.status(404).json({ error: 'Project not found.' });

  const { rows: stages } = await pool.query(
    `SELECT * FROM project_stages WHERE project_id = $1 ORDER BY stage_number`,
    [id]
  );
  const { rows: payments } = await pool.query(
    `SELECT sp.* FROM stage_payments sp
     JOIN project_stages ps ON ps.id = sp.project_stage_id
     WHERE ps.project_id = $1
     ORDER BY ps.stage_number, sp.milestone`,
    [id]
  );

  const stagesWithPayments = stages.map((s) => ({
    ...s,
    payments: payments.filter((p) => p.project_stage_id === s.id),
  }));

  res.json({ ...projectRows[0], stages: stagesWithPayments });
});

// PUT /api/projects/:id/stages/:stageId — edit dates/contract amount
router.put('/:id/stages/:stageId', requireRole('admin', 'estimator'), async (req, res) => {
  const { stageId } = req.params;
  const { start_date, target_date, actual_completion_date, contract_amount } = req.body;

  const { rows } = await pool.query(
    `UPDATE project_stages
     SET start_date = COALESCE($1, start_date),
         target_date = COALESCE($2, target_date),
         actual_completion_date = COALESCE($3, actual_completion_date),
         contract_amount = COALESCE($4, contract_amount)
     WHERE id = $5 RETURNING *`,
    [start_date, target_date, actual_completion_date, contract_amount, stageId]
  );
  if (!rows[0]) return res.status(404).json({ error: 'Stage not found.' });

  // If contract_amount changed, re-derive the 3 milestone amounts to stay consistent.
  if (contract_amount != null) {
    for (const m of MILESTONES) {
      await pool.query(
        `UPDATE stage_payments SET amount = $1 WHERE project_stage_id = $2 AND milestone = $3`,
        [contract_amount * m.percentage, stageId, m.milestone]
      );
    }
  }

  res.json(rows[0]);
});

// PUT /api/payments/:id — update status (Paid / Not Received / Paid via Cheque)
// Mounted separately below since it's not project-scoped in the URL.
export const paymentsRouter = Router();
paymentsRouter.use(requireAuth);
paymentsRouter.put('/:id', requireRole('admin', 'accounts'), async (req, res) => {
  const { id } = req.params;
  const { status, paid_date } = req.body;
  const validStatuses = ['paid', 'not_received', 'paid_via_cheque'];
  if (!validStatuses.includes(status)) {
    return res.status(400).json({ error: `status must be one of: ${validStatuses.join(', ')}` });
  }

  const { rows } = await pool.query(
    `UPDATE stage_payments
     SET status = $1, paid_date = $2, updated_at = now(), updated_by = $3
     WHERE id = $4 RETURNING *`,
    [status, paid_date || null, req.user.id, id]
  );
  if (!rows[0]) return res.status(404).json({ error: 'Payment not found.' });
  res.json(rows[0]);
});

export default router;
