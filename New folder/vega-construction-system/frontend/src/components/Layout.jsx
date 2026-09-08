import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext.jsx';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', roles: ['admin', 'estimator', 'accounts'] },
  { to: '/price-list', label: 'Price List', roles: ['admin', 'estimator', 'accounts'] },
  { to: '/trade-items', label: 'Trade Items (BOQ)', roles: ['admin', 'estimator'] },
  { to: '/projects', label: 'Projects', roles: ['admin', 'estimator', 'accounts'] },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const visibleItems = NAV_ITEMS.filter((item) => item.roles.includes(user?.role));

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          Vega Construction
          <small>Price List · BSR · ROI</small>
        </div>
        <nav>
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => (isActive ? 'active' : '')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="main-content">
        <div className="topbar">
          <div />
          <div className="user-chip">
            {user?.name}
            <span className="role-badge">{user?.role}</span>
            {' · '}
            <a href="#" onClick={(e) => { e.preventDefault(); logout(); navigate('/login'); }}>
              Log out
            </a>
          </div>
        </div>
        {children}
      </main>
    </div>
  );
}
