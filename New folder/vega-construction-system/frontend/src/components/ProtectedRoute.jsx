import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext.jsx';

export default function ProtectedRoute({ children, roles }) {
  const { token, user } = useAuth();

  if (!token) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user?.role)) {
    return <div className="card">You don't have access to this page.</div>;
  }
  return children;
}
