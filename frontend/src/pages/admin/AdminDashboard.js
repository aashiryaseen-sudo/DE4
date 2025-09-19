import React, { useState, useEffect } from 'react';
import { adminAPI } from '../../services/api';
import { 
  Users, 
  FileText, 
  Activity, 
  TrendingUp,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  RefreshCw
} from 'lucide-react';
import { Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import toast from 'react-hot-toast';

const AdminDashboard = () => {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const response = await adminAPI.getDashboard();
      setDashboardData(response.data);
      if (isRefresh) toast.success('Dashboard refreshed');
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    fetchDashboardData(true);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
      </div>
    );
  }

  if (!dashboardData) {
    return (
      <div className="text-center py-12">
        <AlertCircle className="mx-auto h-16 w-16 text-red-300" />
        <h1 className="mt-4 text-2xl font-bold text-gray-900">Failed to Load Dashboard</h1>
        <p className="mt-2 text-gray-600">Please try refreshing the page</p>
      </div>
    );
  }

  const { stats, master_forms, form_versions, customization_requests, recent_operations, active_sessions } = dashboardData;

  // Prepare chart data
  const operationsData = [
    { name: 'Successful', value: stats.successful_operations, color: '#10B981' },
    { name: 'Failed', value: stats.failed_operations, color: '#EF4444' }
  ];

  const requestsData = [
    { name: 'Failed', value: stats.pending_requests, color: '#EF4444' },
    { name: 'Completed', value: stats.customization_requests - stats.pending_requests, color: '#10B981' }
  ];

  const getStatusBadge = (status) => {
    const statusStyles = {
      pending: 'badge-yellow',
      in_progress: 'badge-blue',
      ready_for_review: 'badge-blue',
      under_review: 'badge-blue',
      revision_requested: 'badge-yellow',
      approved: 'badge-green',
      deployed: 'badge-green',
      cancelled: 'badge-red'
    };
    return statusStyles[status] || 'badge-gray';
  };

  const getPriorityColor = (priority) => {
    if (priority === 1) return 'text-red-600';
    if (priority === 2) return 'text-yellow-600';
    return 'text-green-600';
  };

  const successRate = stats.form_operations > 0
    ? ((stats.successful_operations / stats.form_operations) * 100).toFixed(1)
    : '0.0';

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Admin Dashboard</h1>
          <p className="mt-2 text-gray-600">System overview and management</p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="btn-secondary"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="card">
          <div className="card-content">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Users className="h-8 w-8 text-primary-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Total Users</p>
                <p className="text-2xl font-bold text-gray-900">{stats.users}</p>
                <p className="text-xs text-gray-500">{stats.active_sessions} active sessions</p>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-content">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <FileText className="h-8 w-8 text-green-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Master Forms</p>
                <p className="text-2xl font-bold text-gray-900">{stats.master_forms}</p>
                <p className="text-xs text-gray-500">{stats.active_master_forms} active</p>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-content">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Activity className="h-8 w-8 text-blue-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Requests</p>
                <p className="text-2xl font-bold text-gray-900">{stats.customization_requests}</p>
                <p className="text-xs text-gray-500">{stats.pending_requests} pending</p>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-content">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <TrendingUp className="h-8 w-8 text-purple-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Operations</p>
                <p className="text-2xl font-bold text-gray-900">{stats.form_operations}</p>
                <p className="text-xs text-gray-500">
                  {successRate}% success rate
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-semibold text-gray-900">Operations Status</h2>
          </div>
          <div className="card-content">
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={operationsData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={80}
                  dataKey="value"
                >
                  {operationsData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex justify-center space-x-4 mt-4">
              {operationsData.map((entry, index) => (
                <div key={index} className="flex items-center">
                  <div className="w-3 h-3 rounded-full mr-2" style={{ backgroundColor: entry.color }}></div>
                  <span className="text-sm text-gray-600">{entry.name}: {entry.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-semibold text-gray-900">User Prompts</h2>
          </div>
          <div className="card-content">
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={requestsData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={80}
                  dataKey="value"
                >
                  {requestsData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex justify-center space-x-4 mt-4">
              {requestsData.map((entry, index) => (
                <div key={index} className="flex items-center">
                  <div className="w-3 h-3 rounded-full mr-2" style={{ backgroundColor: entry.color }}></div>
                  <span className="text-sm text-gray-600">{entry.name}: {entry.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Tables */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 mb-8">
        {/* Master Forms */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-semibold text-gray-900">Recent Master Forms</h2>
          </div>
          <div className="card-content p-0">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Form
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Version
                    </th>
                    
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {master_forms.slice(0, 5).map((form) => (
                    <tr key={form.id}>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div>
                          <div className="text-sm font-medium text-gray-900">{form.name}</div>
                          <div className="text-sm text-gray-500">{form.form_type}</div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        Current: {form.current_version}
                      </td>
                      
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Recent Form Versions */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-semibold text-gray-900">Recent Form Versions</h2>
          </div>
          <div className="card-content p-0">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Form</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Current</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {form_versions.slice(0, 10).map((v) => (
                    <tr key={v.id}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{v.master_form_name || v.master_form_id}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{v.version}</td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {v.is_current ? (
                          <span className="badge badge-green">Yes</span>
                        ) : (
                          <span className="badge">No</span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{new Date(v.created_at).toLocaleString()}</td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {v.has_xml_content ? (
                          <a
                            href={`/api/admin/form-versions/${v.id}/download`}
                            className="btn-secondary text-xs"
                            download
                          >
                            Download XML
                          </a>
                        ) : (
                          <span className="text-xs text-gray-400">No XML</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* Recent User Prompts */}
        <div className="card">
          <div className="card-header">
          <h2 className="text-lg font-semibold text-gray-900">Recent User Prompts</h2>
          </div>
          <div className="card-content p-0">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Prompt
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Target Sheet
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Time
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {customization_requests.slice(0, 5).map((request) => (
                    <tr key={request.id}>
                    <td className="px-6 py-4">
                      <div className="text-sm text-gray-900 max-w-xs truncate" title={request.prompt}>
                        {request.prompt}
                      </div>
                    </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-500">
                        {request.target_sheet || 'All sheets'}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {(() => {
                          const st = (request.status || '').toLowerCase();
                          const successStates = ['approved', 'deployed', 'completed'];
                          const warningStates = ['pending', 'in_progress', 'ready_for_review', 'under_review'];
                          const dangerStates = ['revision_requested', 'cancelled', 'failed'];
                          const klass = successStates.includes(st)
                            ? 'badge-green'
                            : warningStates.includes(st)
                              ? 'badge-yellow'
                              : dangerStates.includes(st)
                                ? 'badge-red'
                                : 'badge';
                          return (
                            <span className={`badge ${klass}`}>{request.status}</span>
                          );
                        })()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-500">
                        {request.timestamp ? new Date(request.timestamp).toLocaleString() : 'Unknown'}
                      </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
          </div>
        </div>
      </div>

      {/* Active Sessions */}
      <div className="card mb-8 mt-8">
        <div className="card-header">
          <h2 className="text-lg font-semibold text-gray-900">Active Sessions</h2>
        </div>
        <div className="card-content p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    User
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Role
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    IP Address
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Last Activity
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {active_sessions.slice(0, 10).map((session) => (
                  <tr key={session.id}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="h-2 w-2 bg-green-400 rounded-full mr-3"></div>
                        <div className="text-sm font-medium text-gray-900">{session.username}</div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="badge badge-blue capitalize">{session.user_role}</span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {session.ip_address || 'Unknown'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(session.last_activity).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Recent Operations */}
      <div className="card">
        <div className="card-header">
          <h2 className="text-lg font-semibold text-gray-900">Recent Operations</h2>
        </div>
        <div className="card-content p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Operation
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    User
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Time
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {recent_operations.slice(0, 10).map((operation) => (
                  <tr key={operation.id}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div>
                        <div className="text-sm font-medium text-gray-900 capitalize">
                          {operation.operation_type}
                        </div>
                        <div className="text-sm text-gray-500">{operation.operation_description}</div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {operation.username}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {operation.success ? (
                        <CheckCircle className="h-5 w-5 text-green-500" />
                      ) : (
                        <XCircle className="h-5 w-5 text-red-500" />
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(operation.started_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminDashboard;
