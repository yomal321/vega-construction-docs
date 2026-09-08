import React, { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { useAuth } from '../context/AuthContext.jsx';

const FLOORS = ['ground', 'first', 'second', 'third', 'fourth'];

export default function TradeItems() {
  const { token, user } = useAuth();
  const canEdit = user?.role === 'admin' || user?.role === 'estimator';

  const [items, setItems] = useState([]);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [floor, setFloor] = useState('ground');
  const [baseItems, setBaseItems] = useState([]);
  const [allTradeItems, setAllTradeItems] = useState([]);
  const [components, setComponents] = useState([]);
  const [showNewForm, setShowNewForm] = useState(false);
  const [newItem, setNewItem] = useState({ code: '', description: '', unit: '', analysis_qty: 1 });
  const [error, setError] = useState(null);

  async function loadList() {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    const data = await api.get(`/trade-items?${params.toString()}`, token);
    setItems(data);
  }

  async function loadDetail(id, f = floor) {
    setError(null);
    try {
      const data = await api.get(`/trade-items/${id}?floor=${f}`, token);
      setDetail(data);
      setComponents(
        data.resolved.breakdown.map((b) => ({ description: b.description, quantity: b.quantity, unitCost: b.unitCost }))
      );
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => { loadList(); }, [search]); // eslint-disable-line
  useEffect(() => {
    if (selectedId) loadDetail(selectedId, floor);
  }, [selectedId, floor]); // eslint-disable-line

  useEffect(() => {
    api.get('/base-items', token).then(setBaseItems);
    api.get('/trade-items', token).then(setAllTradeItems);
  }, []); // eslint-disable-line

  async function createTradeItem(e) {
    e.preventDefault();
    const created = await api.post('/trade-items', newItem, token);
    setShowNewForm(false);
    setNewItem({ code: '', description: '', unit: '', analysis_qty: 1 });
    await loadList();
    setSelectedId(created.id);
  }

  // ---- Recipe editor (component picker) ----
  const [pickerKind, setPickerKind] = useState('base_item');
  const [pickerTargetId, setPickerTargetId] = useState('');
  const [pickerQty, setPickerQty] = useState('');
  const [recipeRows, setRecipeRows] = useState([]);

  useEffect(() => {
    setRecipeRows(
      detail?.resolved.breakdown.map((b) => ({ description: b.description, quantity: b.quantity })) || []
    );
  }, [detail]);

  function addRecipeLine() {
    if (!pickerTargetId || !pickerQty) return;
    const source = pickerKind === 'base_item'
      ? baseItems.find((b) => b.id === Number(pickerTargetId))
      : allTradeItems.find((t) => t.id === Number(pickerTargetId));

    setRecipeRows((rows) => [
      ...rows,
      {
        component_kind: pickerKind,
        base_item_id: pickerKind === 'base_item' ? Number(pickerTargetId) : null,
        child_trade_item_id: pickerKind === 'trade_item' ? Number(pickerTargetId) : null,
        quantity: Number(pickerQty),
        description: source?.description,
      },
    ]);
    setPickerTargetId('');
    setPickerQty('');
  }

  async function saveRecipe() {
    try {
      await api.post(`/trade-items/${selectedId}/components`, { components: recipeRows }, token);
      await loadDetail(selectedId, floor);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <div className="topbar">
        <h1>Trade Items — Rate Analysis</h1>
        {canEdit && <button onClick={() => setShowNewForm((v) => !v)}>{showNewForm ? 'Cancel' : '+ New trade item'}</button>}
      </div>

      {showNewForm && (
        <form className="card" onSubmit={createTradeItem}>
          <div className="grid-3">
            <div className="field"><label>Code</label><input value={newItem.code} onChange={(e) => setNewItem({ ...newItem, code: e.target.value })} placeholder="e.g. 04.01" /></div>
            <div className="field"><label>Unit</label><input value={newItem.unit} onChange={(e) => setNewItem({ ...newItem, unit: e.target.value })} placeholder="Cube / Sqr / L.ft" required /></div>
            <div className="field"><label>Analysis basis (qty)</label><input type="number" step="0.0001" value={newItem.analysis_qty} onChange={(e) => setNewItem({ ...newItem, analysis_qty: e.target.value })} /></div>
          </div>
          <div className="field"><label>Description</label><input style={{ width: '100%' }} value={newItem.description} onChange={(e) => setNewItem({ ...newItem, description: e.target.value })} required /></div>
          <button type="submit">Create</button>
        </form>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 20 }}>
        <div className="card" style={{ maxHeight: 640, overflowY: 'auto' }}>
          <input placeholder="Search trade items…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: '100%', marginBottom: 12 }} />
          {items.map((item) => (
            <div
              key={item.id}
              onClick={() => setSelectedId(item.id)}
              style={{
                padding: '8px 10px', borderRadius: 4, cursor: 'pointer', marginBottom: 4,
                background: selectedId === item.id ? 'rgba(232,163,61,0.15)' : 'transparent',
              }}
            >
              <div style={{ fontSize: 12, color: 'var(--color-steel)' }} className="numeric">{item.code || '—'}</div>
              <div>{item.description}</div>
            </div>
          ))}
        </div>

        <div>
          {!detail && <div className="card">Select a trade item on the left, or create a new one.</div>}
          {detail && (
            <div className="card">
              <div className="topbar" style={{ marginBottom: 8 }}>
                <div>
                  <h2 style={{ marginBottom: 2 }}>{detail.description}</h2>
                  <div style={{ fontSize: 12, color: 'var(--color-steel)' }}>
                    Unit: {detail.unit} · Analysis basis: {detail.analysis_qty} {detail.unit}
                  </div>
                </div>
                <select value={floor} onChange={(e) => setFloor(e.target.value)}>
                  {FLOORS.map((f) => <option key={f} value={f}>{f[0].toUpperCase() + f.slice(1)} floor</option>)}
                </select>
              </div>

              <div className="kpi" style={{ marginBottom: 16 }}>
                <div className="label">Resolved rate ({floor} floor)</div>
                <div className="value">LKR {detail.resolved.rate.toLocaleString(undefined, { maximumFractionDigits: 2 })} / {detail.unit}</div>
                {detail.resolved.multiplier !== 1 && (
                  <div style={{ fontSize: 12, color: 'var(--color-steel)' }}>
                    Base rate {detail.resolved.baseRate.toFixed(2)} × {detail.resolved.multiplier} floor multiplier
                  </div>
                )}
              </div>

              <h3 style={{ fontSize: 14 }}>Recipe</h3>
              <table style={{ marginBottom: 12 }}>
                <thead><tr><th>Component</th><th>Qty</th><th>Unit cost</th><th>Line cost</th></tr></thead>
                <tbody>
                  {detail.resolved.breakdown.map((b, i) => (
                    <tr key={i}>
                      <td>{b.description}{b.note ? <span style={{ color: 'var(--color-steel)', fontSize: 11 }}> ({b.note})</span> : null}</td>
                      <td className="numeric">{b.quantity}</td>
                      <td className="numeric">{b.unitCost.toLocaleString()}</td>
                      <td className="numeric">{b.lineCost.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                    </tr>
                  ))}
                  {detail.resolved.breakdown.length === 0 && (
                    <tr><td colSpan={4} style={{ color: 'var(--color-steel)' }}>No recipe components yet — add some below.</td></tr>
                  )}
                </tbody>
              </table>

              {canEdit && (
                <>
                  <h3 style={{ fontSize: 14 }}>Add / edit components</h3>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                    <select value={pickerKind} onChange={(e) => setPickerKind(e.target.value)}>
                      <option value="base_item">Base item</option>
                      <option value="trade_item">Another trade item</option>
                    </select>
                    <select value={pickerTargetId} onChange={(e) => setPickerTargetId(e.target.value)} style={{ minWidth: 220 }}>
                      <option value="">Select…</option>
                      {(pickerKind === 'base_item' ? baseItems : allTradeItems.filter((t) => t.id !== selectedId))
                        .map((o) => <option key={o.id} value={o.id}>{o.description}</option>)}
                    </select>
                    <input type="number" step="0.0001" placeholder="Quantity" value={pickerQty} onChange={(e) => setPickerQty(e.target.value)} style={{ width: 100 }} />
                    <button type="button" onClick={addRecipeLine}>Add line</button>
                  </div>

                  {recipeRows.length > 0 && (
                    <ul style={{ fontSize: 13, marginBottom: 12 }}>
                      {recipeRows.map((r, i) => (
                        <li key={i}>
                          {r.quantity} × {r.description}
                          <button className="secondary" style={{ marginLeft: 8, padding: '2px 8px' }}
                            onClick={() => setRecipeRows((rows) => rows.filter((_, idx) => idx !== i))}>
                            remove
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <button onClick={saveRecipe}>Save recipe</button>
                </>
              )}

              {error && <p style={{ color: 'var(--color-danger)', marginTop: 12 }}>{error}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
