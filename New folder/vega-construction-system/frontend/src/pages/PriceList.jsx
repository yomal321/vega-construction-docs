import React, { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { useAuth } from '../context/AuthContext.jsx';

const CATEGORIES = ['material', 'labour', 'plant'];

export default function PriceList() {
  const { token, user } = useAuth();
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState({});
  const [showNewForm, setShowNewForm] = useState(false);
  const [newItem, setNewItem] = useState({ category: 'material', description: '', unit: '', unit_price: '', trade_group: '', code: '' });

  const canEdit = user?.role === 'admin' || user?.role === 'estimator';

  async function load() {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    if (category) params.set('category', category);
    const data = await api.get(`/base-items?${params.toString()}`, token);
    setItems(data);
  }

  useEffect(() => { load(); }, [search, category]); // eslint-disable-line

  function startEdit(item) {
    setEditingId(item.id);
    setDraft({ description: item.description, unit: item.unit, unit_price: item.unit_price });
  }

  async function saveEdit(id) {
    await api.put(`/base-items/${id}`, draft, token);
    setEditingId(null);
    load();
  }

  async function createItem(e) {
    e.preventDefault();
    await api.post('/base-items', { ...newItem, unit_price: Number(newItem.unit_price) }, token);
    setShowNewForm(false);
    setNewItem({ category: 'material', description: '', unit: '', unit_price: '', trade_group: '', code: '' });
    load();
  }

  return (
    <div>
      <div className="topbar">
        <h1>Price List</h1>
        {canEdit && <button onClick={() => setShowNewForm((v) => !v)}>{showNewForm ? 'Cancel' : '+ Add item'}</button>}
      </div>

      {showNewForm && (
        <form className="card" onSubmit={createItem}>
          <div className="grid-3">
            <div className="field">
              <label>Category</label>
              <select value={newItem.category} onChange={(e) => setNewItem({ ...newItem, category: e.target.value })}>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Trade group</label>
              <input value={newItem.trade_group} onChange={(e) => setNewItem({ ...newItem, trade_group: e.target.value })} placeholder="e.g. CONCRETE" />
            </div>
            <div className="field">
              <label>Code</label>
              <input value={newItem.code} onChange={(e) => setNewItem({ ...newItem, code: e.target.value })} placeholder="e.g. M-026" />
            </div>
            <div className="field">
              <label>Description</label>
              <input value={newItem.description} onChange={(e) => setNewItem({ ...newItem, description: e.target.value })} required />
            </div>
            <div className="field">
              <label>Unit</label>
              <input value={newItem.unit} onChange={(e) => setNewItem({ ...newItem, unit: e.target.value })} placeholder="Bag / Day / Cube" required />
            </div>
            <div className="field">
              <label>Unit price (LKR)</label>
              <input type="number" step="0.01" value={newItem.unit_price} onChange={(e) => setNewItem({ ...newItem, unit_price: e.target.value })} required />
            </div>
          </div>
          <button type="submit">Save item</button>
        </form>
      )}

      <div className="card">
        <div className="grid-2" style={{ marginBottom: 16 }}>
          <input placeholder="Search by name or code…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <table>
          <thead>
            <tr>
              <th>Code</th><th>Category</th><th>Group</th><th>Description</th><th>Unit</th>
              <th>Price</th><th>Last updated</th><th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td className="numeric">{item.code || '—'}</td>
                <td>{item.category}</td>
                <td>{item.trade_group || '—'}</td>
                <td>
                  {editingId === item.id
                    ? <input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
                    : item.description}
                </td>
                <td>
                  {editingId === item.id
                    ? <input style={{ width: 70 }} value={draft.unit} onChange={(e) => setDraft({ ...draft, unit: e.target.value })} />
                    : item.unit}
                </td>
                <td className="numeric">
                  {editingId === item.id
                    ? <input type="number" step="0.01" style={{ width: 90 }} value={draft.unit_price} onChange={(e) => setDraft({ ...draft, unit_price: e.target.value })} />
                    : Number(item.unit_price).toLocaleString()}
                </td>
                <td style={{ fontSize: 12, color: 'var(--color-steel)' }}>
                  {new Date(item.updated_at).toLocaleDateString()} {item.updated_by_name ? `· ${item.updated_by_name}` : ''}
                </td>
                <td>
                  {canEdit && (editingId === item.id
                    ? <button onClick={() => saveEdit(item.id)}>Save</button>
                    : <button className="secondary" onClick={() => startEdit(item)}>Edit</button>)}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--color-steel)' }}>No items found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
