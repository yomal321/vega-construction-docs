import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';

import authRoutes from './routes/auth.routes.js';
import baseItemsRoutes from './routes/baseItems.routes.js';
import tradeItemsRoutes from './routes/tradeItems.routes.js';
import projectsRoutes, { paymentsRouter } from './routes/projects.routes.js';
import bsrRoutes from './routes/bsr.routes.js';
import expensesRoutes from './routes/expenses.routes.js';
import dashboardRoutes from './routes/dashboard.routes.js';

dotenv.config();

const app = express();

app.use(cors({ origin: process.env.CORS_ORIGIN || '*' }));
app.use(express.json());

app.get('/api/health', (req, res) => res.json({ ok: true }));

app.use('/api/auth', authRoutes);
app.use('/api/base-items', baseItemsRoutes);
app.use('/api/trade-items', tradeItemsRoutes);
app.use('/api/projects', projectsRoutes);
app.use('/api/payments', paymentsRouter);
app.use('/api', bsrRoutes);      // mounts /api/projects/:id/bsr and /api/bsr-items/:id
app.use('/api', expensesRoutes); // mounts /api/projects/:id/expenses and /api/expenses/:id
app.use('/api', dashboardRoutes);// mounts /api/projects/:id/dashboard and /api/dashboard/summary

// Centralized error handler — catches anything thrown/rejected in route handlers
// that wasn't already caught locally, so the API never leaks a stack trace.
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: 'Something went wrong on the server.' });
});

const PORT = process.env.PORT || 4000;
app.listen(PORT, () => {
  console.log(`Vega Construction API listening on port ${PORT}`);
});
