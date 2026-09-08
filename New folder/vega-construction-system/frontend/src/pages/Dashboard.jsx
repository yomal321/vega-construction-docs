import React, { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { useAuth } from '../context/AuthContext.jsx';

export default function Dashboard() {
  const { token } = useAuth();
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.get('/dashboard/summary', token).then(setSummary);
  }, []); // eslint-disable-line

  if (!summary) return <div className="card">Loading…</div>;

  return (
    <div>
      <h1>Portfolio Dashboard</h1>
      <div className="grid-3">
        <div className="card kpi"><div className="label">Active projects</div><div className="value">{summary.projectCount}</div></div>
        <div className="card kpi"><div className="label">Total received</div><div className="value">LKR {summary.totalReceived.toLocaleString()}</div></div>
        <div className="card kpi"><div className="label">Total outstanding</div><div className="value">LKR {summary.totalOutstanding.toLocaleString()}</div></div>
        <div className="card kpi"><div className="label">Total expenses</div><div className="value">LKR {summary.totalExpenses.toLocaleString()}</div></div>
        <div className="card kpi">
          <div className="label">Net income (all projects)</div>
          <div className="value" style={{ color: summary.netIncome >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>
            LKR {summary.netIncome.toLocaleString()}
          </div>
        </div>
      </div>
    </div>
  );
}
