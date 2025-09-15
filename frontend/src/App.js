import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Layout from './components/Layout/Layout';
import ProtectedRoute from './components/ProtectedRoute';

// Pages
import Login from './pages/auth/Login';
import Register from './pages/auth/Register';
import Upload from './pages/Upload';
import Files from './pages/Files';
import AdminDashboard from './pages/admin/AdminDashboard';

const AppRoutes = () => {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      
      {/* Protected routes */}
      <Route path="/" element={
        <ProtectedRoute>
          <Layout>
            <Navigate to="/upload" replace />
          </Layout>
        </ProtectedRoute>
      } />
      
      <Route path="/upload" element={
        <ProtectedRoute>
          <Layout>
            <Upload />
          </Layout>
        </ProtectedRoute>
      } />
      
      <Route path="/files" element={
        <ProtectedRoute>
          <Layout>
            <Files />
          </Layout>
        </ProtectedRoute>
      } />
      
      {/* Admin only routes */}
      <Route path="/admin" element={
        <ProtectedRoute adminOnly>
          <Layout>
            <AdminDashboard />
          </Layout>
        </ProtectedRoute>
      } />
      
      {/* Catch all route */}
      <Route path="*" element={
        isAuthenticated() ? 
          <Navigate to="/upload" replace /> : 
          <Navigate to="/login" replace />
      } />
    </Routes>
  );
};

function App() {
  return (
    <Router>
      <AuthProvider>
        <div className="App">
          <AppRoutes />
          <Toaster
            position="top-right"
            toastOptions={{
              duration: 4000,
              style: {
                background: '#363636',
                color: '#fff',
              },
              success: {
                duration: 3000,
                style: {
                  background: '#10B981',
                },
              },
              error: {
                duration: 5000,
                style: {
                  background: '#EF4444',
                },
              },
            }}
          />
        </div>
      </AuthProvider>
    </Router>
  );
}

export default App;
