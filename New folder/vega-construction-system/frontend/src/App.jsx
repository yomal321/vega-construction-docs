import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Login from './pages/Login.jsx';
import Dashboard from './pages/Dashboard.jsx';
import PriceList from './pages/PriceList.jsx';
import TradeItems from './pages/TradeItems.jsx';
import Projects from './pages/Projects.jsx';
import ProjectDetail from './pages/ProjectDetail.jsx';
import Layout from './components/Layout.jsx';
import ProtectedRoute from './components/ProtectedRoute.jsx';

function Page({ children, roles }) {
  return (
    <ProtectedRoute roles={roles}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Page><Dashboard /></Page>} />
      <Route path="/price-list" element={<Page><PriceList /></Page>} />
      <Route path="/trade-items" element={<Page roles={['admin', 'estimator']}><TradeItems /></Page>} />
      <Route path="/projects" element={<Page><Projects /></Page>} />
      <Route path="/projects/:id" element={<Page><ProjectDetail /></Page>} />
    </Routes>
  );
}
