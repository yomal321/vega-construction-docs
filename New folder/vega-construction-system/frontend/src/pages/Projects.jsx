import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAuth } from '../context/AuthContext.jsx';

export default function Projects() {
  const { token, user } = useAuth();
  const canCreate = user?.role === 'admin' || user?.role === 'estimator';
  const [projects, setProjects] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', client_name: '', site_address: '', stage_count: 4 });

  async function load() {
    setProjects(await api.get('/projects', token));
  }
  useEffect(() => { load(); }, []); // eslint-disable-line

  async function createProject(e) {
    e.preventDefault();
    await api.post('/projects', { ...form, stage_count: Number(form.stage_count) }, token);
    setShowForm(false);
    setForm({ name: '', client_name: '', site_address: '', stage_count: 4 });
    load();
  }

  return (
    <div>
      <div className="topbar">
        <h1>Projects</h1>
        {canCreate && <button onClick={() => setShowForm((v) => !v)}>{showForm ? 'Cancel' : '+ New project'}</button>}
      </div>

      {showForm && (
        <form className="card" onSubmit={createProject}>
          <div className="grid-2">
            <div className="field"><label>Project name</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
            <div className="field"><label>Client</label><input value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} required /></div>
            <div className="field"><label>Site address</label><input value={form.site_address} onChange={(e) => setForm({ ...form, site_address: e.target.value })} /></div>
            <div className="field">
              <label>Number of construction stages</label>
              <input type="number" min="1" value={form.stage_count} onChange={(e) => setForm({ ...form, stage_count: e.target.value })} required />
            </div>
          </div>
          <button type="submit">Create project</button>
        </form>
      )}

      <div className="card">
        <table>
          <thead><tr><th>Project</th><th>Client</th><th>Stages</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td>{p.client_name}</td>
                <td className="numeric">{p.stage_count}</td>
                <td style={{ fontSize: 12, color: 'var(--color-steel)' }}>{new Date(p.created_at).toLocaleDateString()}</td>
                <td><Link to={`/projects/${p.id}`}>Open →</Link></td>
              </tr>
            ))}
            {projects.length === 0 && <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--color-steel)' }}>No projects yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
