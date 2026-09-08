import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAuth } from '../context/AuthContext.jsx';

const TABS = ['Overview', 'BSR', 'Stages & Payments', 'Expenses'];
const FLOORS = ['ground', 'first', 'second', 'third', 'fourth'];
const EXPENSE_CATEGORIES = ['labour', 'material', 'sub_contractor', 'machinery', 'transport', 'other'];
const STATUS_LABELS = { paid: 'Paid', not_received: 'Not Received', paid_via_cheque: 'Paid via Cheque' };

export default function ProjectDetail() {
  const { id } = useParams();
  const { token, user } = useAuth();
  const [tab, setTab] = useState('Overview');
  const [project, setProject] = useState(null);

  async function loadProject() {
    setProject(await api.get(`/projects/${id}`, token));
  }
  useEffect(() => { loadProject(); }, [id]); // eslint-disable-line

  if (!project) return <div className="card">Loading…</div>;

  return (
    <div>
      <div className="topbar">
        <div>
          <h1 style={{ marginBottom: 2 }}>{project.name}</h1>
          <div style={{ color: 'var(--color-steel)', fontSize: 13 }}>{project.client_name} · {project.site_address}</div>
        </div>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>

      {tab === 'Overview' && <OverviewTab projectId={id} />}
      {tab === 'BSR' && <BSRTab projectId={id} />}
      {tab === 'Stages & Payments' && <PaymentsTab project={project} onChange={loadProject} />}
      {tab === 'Expenses' && <ExpensesTab project={project} />}
    </div>
  );
}

// ---------------- Overview / ROI ----------------
function OverviewTab({ projectId }) {
  const { token } = useAuth();
  const [dashboard, setDashboard] = useState(null);

  useEffect(() => {
    api.get(`/projects/${projectId}/dashboard`, token).then(setDashboard);
  }, [projectId]); // eslint-disable-line

  if (!dashboard) return <div className="card">Loading…</div>;

  return (
    <>
      <div className="grid-3">
        <div className="card kpi"><div className="label">Payments received</div><div className="value">LKR {dashboard.paymentsReceived.toLocaleString()}</div></div>
        <div className="card kpi"><div className="label">Outstanding</div><div className="value">LKR {dashboard.outstanding.toLocaleString()}</div></div>
        <div className="card kpi"><div className="label">Cheque payments</div><div className="value">LKR {dashboard.chequePayments.toLocaleString()}</div></div>
        <div className="card kpi"><div className="label">Total expenses</div><div className="value">LKR {dashboard.totalExpenses.toLocaleString()}</div></div>
        <div className="card kpi"><div className="label">Net income</div><div className="value" style={{ color: dashboard.netIncome >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>LKR {dashboard.netIncome.toLocaleString()}</div></div>
        <div className="card kpi"><div className="label">ROI</div><div className="value">{dashboard.roiPercent != null ? `${dashboard.roiPercent.toFixed(1)}%` : '—'}</div></div>
      </div>

      <div className="card">
        <h3>Expenses by category</h3>
        <table>
          <thead><tr><th>Category</th><th>Total</th></tr></thead>
          <tbody>
            {dashboard.expenseByCategory.map((row) => (
              <tr key={row.category}><td>{row.category.replace('_', ' ')}</td><td className="numeric">LKR {row.total.toLocaleString()}</td></tr>
            ))}
            {dashboard.expenseByCategory.length === 0 && <tr><td colSpan={2} style={{ color: 'var(--color-steel)' }}>No expenses logged yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ---------------- BSR ----------------
function BSRTab({ projectId }) {
  const { token, user } = useAuth();
  const canEdit = user?.role === 'admin' || user?.role === 'estimator';
  const [bsr, setBsr] = useState(null);
  const [tradeItems, setTradeItems] = useState([]);
  const [form, setForm] = useState({ trade_item_id: '', quantity: '', floor: 'ground' });

  async function load() {
    setBsr(await api.get(`/projects/${projectId}/bsr`, token));
  }
  useEffect(() => { load(); api.get('/trade-items', token).then(setTradeItems); }, [projectId]); // eslint-disable-line

  async function addItem(e) {
    e.preventDefault();
    await api.post(`/projects/${projectId}/bsr/items`, { ...form, quantity: Number(form.quantity) }, token);
    setForm({ trade_item_id: '', quantity: '', floor: 'ground' });
    load();
  }

  async function removeItem(lineId) {
    await api.del(`/bsr-items/${lineId}`, token);
    load();
  }

  if (!bsr) return <div className="card">Loading…</div>;

  return (
    <>
      {canEdit && (
        <form className="card" onSubmit={addItem}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="field" style={{ minWidth: 260 }}>
              <label>Trade item</label>
              <select value={form.trade_item_id} onChange={(e) => setForm({ ...form, trade_item_id: e.target.value })} required>
                <option value="">Select…</option>
                {tradeItems.map((t) => <option key={t.id} value={t.id}>{t.description}</option>)}
              </select>
            </div>
            <div className="field"><label>Quantity</label><input type="number" step="0.0001" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} required style={{ width: 100 }} /></div>
            <div className="field">
              <label>Floor</label>
              <select value={form.floor} onChange={(e) => setForm({ ...form, floor: e.target.value })}>
                {FLOORS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            <button type="submit" style={{ marginBottom: 14 }}>Add to BSR</button>
          </div>
        </form>
      )}

      <div className="card">
        <table>
          <thead><tr><th>Item</th><th>Floor</th><th>Qty</th><th>Rate (LKR)</th><th>Line total</th><th></th></tr></thead>
          <tbody>
            {bsr.lineItems.map((li) => (
              <tr key={li.id}>
                <td>{li.description}</td>
                <td>{li.floor}</td>
                <td className="numeric">{li.quantity}</td>
                <td className="numeric">{Number(li.rate_snapshot).toLocaleString()}</td>
                <td className="numeric">{Number(li.line_total).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                <td>{canEdit && <button className="secondary" onClick={() => removeItem(li.id)}>Remove</button>}</td>
              </tr>
            ))}
            {bsr.lineItems.length === 0 && <tr><td colSpan={6} style={{ color: 'var(--color-steel)' }}>No items added to this BSR yet.</td></tr>}
          </tbody>
          {bsr.lineItems.length > 0 && (
            <tfoot>
              <tr><td colSpan={4} style={{ textAlign: 'right', fontWeight: 600 }}>Grand total</td><td className="numeric" style={{ fontWeight: 600 }}>LKR {bsr.grandTotal.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td><td /></tr>
            </tfoot>
          )}
        </table>
      </div>
    </>
  );
}

// ---------------- Stages & Payments ----------------
function PaymentsTab({ project, onChange }) {
  const { token, user } = useAuth();
  const canEditStage = user?.role === 'admin' || user?.role === 'estimator';
  const canEditPayment = user?.role === 'admin' || user?.role === 'accounts';

  async function updatePaymentStatus(paymentId, status) {
    await api.put(`/payments/${paymentId}`, { status, paid_date: status !== 'not_received' ? new Date().toISOString().slice(0, 10) : null }, token);
    onChange();
  }

  async function updateStageDates(stageId, field, value) {
    await api.put(`/projects/${project.id}/stages/${stageId}`, { [field]: value }, token);
    onChange();
  }

  return (
    <>
      {project.stages.map((stage) => (
        <div className="card" key={stage.id}>
          <div className="topbar" style={{ marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{stage.name}</h3>
            <div className="numeric">Contract amount: LKR {Number(stage.contract_amount).toLocaleString()}</div>
          </div>

          {canEditStage && (
            <div className="grid-3" style={{ marginBottom: 12 }}>
              <div className="field"><label>Start date</label><input type="date" defaultValue={stage.start_date?.slice(0,10) || ''} onBlur={(e) => updateStageDates(stage.id, 'start_date', e.target.value)} /></div>
              <div className="field"><label>Target date</label><input type="date" defaultValue={stage.target_date?.slice(0,10) || ''} onBlur={(e) => updateStageDates(stage.id, 'target_date', e.target.value)} /></div>
              <div className="field"><label>Actual completion</label><input type="date" defaultValue={stage.actual_completion_date?.slice(0,10) || ''} onBlur={(e) => updateStageDates(stage.id, 'actual_completion_date', e.target.value)} /></div>
            </div>
          )}

          <table>
            <thead><tr><th>Milestone</th><th>%</th><th>Amount</th><th>Status</th><th>Paid date</th></tr></thead>
            <tbody>
              {stage.payments.map((p) => (
                <tr key={p.id}>
                  <td style={{ textTransform: 'capitalize' }}>{p.milestone}</td>
                  <td className="numeric">{(Number(p.percentage) * 100).toFixed(0)}%</td>
                  <td className="numeric">LKR {Number(p.amount).toLocaleString()}</td>
                  <td>
                    {canEditPayment ? (
                      <select value={p.status} onChange={(e) => updatePaymentStatus(p.id, e.target.value)}>
                        {Object.entries(STATUS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    ) : (
                      <span className={`pill pill-${p.status}`}>{STATUS_LABELS[p.status]}</span>
                    )}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--color-steel)' }}>{p.paid_date ? new Date(p.paid_date).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}

// ---------------- Expenses ----------------
function ExpensesTab({ project }) {
  const { token, user } = useAuth();
  const canEdit = user?.role === 'admin' || user?.role === 'accounts';
  const [expenses, setExpenses] = useState([]);
  const [form, setForm] = useState({ vendor_name: '', category: 'material', invoice_ref: '', amount: '', project_stage_id: '', notes: '' });

  async function load() {
    setExpenses(await api.get(`/projects/${project.id}/expenses`, token));
  }
  useEffect(() => { load(); }, [project.id]); // eslint-disable-line

  async function addExpense(e) {
    e.preventDefault();
    await api.post(`/projects/${project.id}/expenses`, { ...form, amount: Number(form.amount), project_stage_id: form.project_stage_id || null }, token);
    setForm({ vendor_name: '', category: 'material', invoice_ref: '', amount: '', project_stage_id: '', notes: '' });
    load();
  }

  return (
    <>
      {canEdit && (
        <form className="card" onSubmit={addExpense}>
          <div className="grid-3">
            <div className="field"><label>Vendor</label><input value={form.vendor_name} onChange={(e) => setForm({ ...form, vendor_name: e.target.value })} required /></div>
            <div className="field">
              <label>Category</label>
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{c.replace('_', ' ')}</option>)}
              </select>
            </div>
            <div className="field"><label>Invoice ref</label><input value={form.invoice_ref} onChange={(e) => setForm({ ...form, invoice_ref: e.target.value })} /></div>
            <div className="field"><label>Amount (LKR)</label><input type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required /></div>
            <div className="field">
              <label>Stage</label>
              <select value={form.project_stage_id} onChange={(e) => setForm({ ...form, project_stage_id: e.target.value })}>
                <option value="">— unassigned —</option>
                {project.stages.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="field"><label>Notes</label><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
          </div>
          <button type="submit">Log expense</button>
        </form>
      )}

      <div className="card">
        <table>
          <thead><tr><th>Date</th><th>Vendor</th><th>Category</th><th>Invoice</th><th>Stage</th><th>Amount</th></tr></thead>
          <tbody>
            {expenses.map((e) => (
              <tr key={e.id}>
                <td style={{ fontSize: 12 }}>{new Date(e.expense_date).toLocaleDateString()}</td>
                <td>{e.vendor_name}</td>
                <td style={{ textTransform: 'capitalize' }}>{e.category.replace('_', ' ')}</td>
                <td className="numeric">{e.invoice_ref || '—'}</td>
                <td>{e.stage_name || '—'}</td>
                <td className="numeric">LKR {Number(e.amount).toLocaleString()}</td>
              </tr>
            ))}
            {expenses.length === 0 && <tr><td colSpan={6} style={{ color: 'var(--color-steel)' }}>No expenses logged yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
