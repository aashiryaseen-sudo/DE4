import React, { createContext, useContext, useState, useEffect } from 'react';
import { authAPI } from '../services/api';
import toast from 'react-hot-toast';

const AuthContext = createContext();

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionToken, setSessionToken] = useState(null);

  useEffect(() => {
    // Check for existing session on app load
    const token = localStorage.getItem('sessionToken');
    const userData = localStorage.getItem('user');
    
    if (token && userData) {
      setSessionToken(token);
      setUser(JSON.parse(userData));
    }
    setLoading(false);
  }, []);

  const login = async (credentials) => {
    try {
      const response = await authAPI.login(credentials);
      const { user: userData, session_token } = response.data;
      
      setUser(userData);
      setSessionToken(session_token);
      
      localStorage.setItem('sessionToken', session_token);
      localStorage.setItem('user', JSON.stringify(userData));
      
      toast.success(`Welcome back, ${userData.full_name || userData.username}!`);
      return { success: true };
    } catch (error) {
      const message = error.response?.data?.detail || 'Login failed';
      toast.error(message);
      return { success: false, error: message };
    }
  };

  const register = async (userData) => {
    try {
      const response = await authAPI.register(userData);
      toast.success('Account created successfully! Please login.');
      return { success: true, data: response.data };
    } catch (error) {
      const message = error.response?.data?.detail || 'Registration failed';
      toast.error(message);
      return { success: false, error: message };
    }
  };

  const logout = async () => {
    try {
      await authAPI.logout();
    } catch (error) {
      // Continue with logout even if API call fails
      console.error('Logout API call failed:', error);
    } finally {
      setUser(null);
      setSessionToken(null);
      localStorage.removeItem('sessionToken');
      localStorage.removeItem('user');
      toast.success('Logged out successfully');
    }
  };

  const isAdmin = () => {
    return user?.role === 'admin';
  };

  const isAuthenticated = () => {
    return !!user && !!sessionToken;
  };

  const value = {
    user,
    sessionToken,
    loading,
    login,
    register,
    logout,
    isAdmin,
    isAuthenticated,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
