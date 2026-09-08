import { Router } from 'express';
import { pool } from '../config/db.js';
import { requireAuth } from '../middleware/auth.js';

const router = Router();
router.use(requireAuth);

// GET /api/projects/:projectId/dashboard
// Income = sum of stage_payments marked 'paid' or 'paid_via_cheque'
// Expenses = sum of all expense rows
// Outstanding = sum of stage_payments still 'not_received'
router.get('/projects/:projectId/dashboard', async (req, res) => {
  const { projectId } = req.params;

  const { rows: incomeRows } = await pool.query(
    `SELECT
       COALESCE(SUM(amount) FILTER (WHERE status IN ('paid','paid_via_cheque')), 0) AS payments_received,
       COALESCE(SUM(amount) FILTER (WHERE status = 'not_received'), 0) AS outstanding,
       COALESCE(SUM(amount) FILTER (WHERE status = 'paid_via_cheque'), 0) AS cheque_payments,
       COALESCE(SUM(amount), 0) AS total_contract_value
     FROM stage_payments sp
     JOIN project_stages ps ON ps.id = sp.project_stage_id
     WHERE ps.project_id = $1`,
    [projectId]
  );

  const { rows: expenseByCategory } = await pool.query(
    `SELECT category, COALESCE(SUM(amount), 0) AS total
     FROM expenses WHERE project_id = $1
     GROUP BY category`,
    [projectId]
  );

  const { rows: expenseTotalRows } = await pool.query(
    `SELECT COALESCE(SUM(amount), 0) AS total_expenses FROM expenses WHERE project_id = $1`,
    [projectId]
  );

  const income = incomeRows[0];
  const totalExpenses = Number(expenseTotalRows[0].total_expenses);
  const paymentsReceived = Number(income.payments_received);
  const netIncome = paymentsReceived - totalExpenses;
  const roi = totalExpenses > 0 ? (netIncome / totalExpenses) * 100 : null;

  res.json({
    paymentsReceived,
    outstanding: Number(income.outstanding),
    chequePayments: Number(income.cheque_payments),
    totalContractValue: Number(income.total_contract_value),
    totalExpenses,
    expenseByCategory: expenseByCategory.map((r) => ({ category: r.category, total: Number(r.total) })),
    netIncome,
    roiPercent: roi,
  });
});

// GET /api/dashboard/summary — portfolio-wide totals across all projects
router.get('/dashboard/summary', async (req, res) => {
  const { rows } = await pool.query(
    `SELECT
       (SELECT COUNT(*) FROM projects) AS project_count,
       (SELECT COALESCE(SUM(amount),0) FROM stage_payments WHERE status IN ('paid','paid_via_cheque')) AS total_received,
       (SELECT COALESCE(SUM(amount),0) FROM stage_payments WHERE status = 'not_received') AS total_outstanding,
       (SELECT COALESCE(SUM(amount),0) FROM expenses) AS total_expenses`
  );
  const r = rows[0];
  res.json({
    projectCount: Number(r.project_count),
    totalReceived: Number(r.total_received),
    totalOutstanding: Number(r.total_outstanding),
    totalExpenses: Number(r.total_expenses),
    netIncome: Number(r.total_received) - Number(r.total_expenses),
  });
});

export default router;
