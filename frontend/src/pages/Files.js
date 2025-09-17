import React, { useState, useEffect } from 'react';
import { fileAPI, systemAPI } from '../services/api';
import { 
  Edit3, 
  Download, 
  Send, 
  FileText, 
  Clock,
  User,
  AlertCircle,
  CheckCircle,
  Loader2
} from 'lucide-react';
import toast from 'react-hot-toast';

const Files = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editPrompt, setEditPrompt] = useState('');
  const [targetSheet, setTargetSheet] = useState('');
  const [editing, setEditing] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    fetchStatus();
  }, []);

  const fetchStatus = async () => {
    try {
      const response = await systemAPI.getStatus();
      setStatus(response.data);
    } catch (error) {
      console.error('Failed to fetch status:', error);
      toast.error('Failed to load file status');
    } finally {
      setLoading(false);
    }
  };

  const handleAIEdit = async (e) => {
    e.preventDefault();
    if (!editPrompt.trim()) return;

    setEditing(true);
    try {
      const response = await fileAPI.aiEdit(editPrompt, targetSheet || null);
      
      if (response.data.success) {
        toast.success('AI edit applied successfully!');
        setEditPrompt('');
        setTargetSheet('');
        await fetchStatus(); // Refresh status
      } else {
        toast.error(response.data.error || 'AI edit failed');
      }
    } catch (error) {
      console.error('AI edit failed:', error);
      const errorMessage = error.response?.data?.detail || error.message || 'AI edit failed. Please try again.';
      toast.error(errorMessage);
    } finally {
      setEditing(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const response = await fileAPI.export();
      
      // Create blob and download
      const blob = new Blob([response.data], { type: 'application/xml' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      // Get filename from headers or use default
      const contentDisposition = response.headers['content-disposition'];
      let filename = 'form.xml';
      if (contentDisposition) {
        const matches = contentDisposition.match(/filename="?([^"]+)"?/);
        if (matches) filename = matches[1];
      }
      
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      
      toast.success('File exported successfully!');
    } catch (error) {
      console.error('Export failed:', error);
      toast.error('Export failed. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
      </div>
    );
  }

  if (!status?.has_file_uploaded) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="text-center py-12">
          <FileText className="mx-auto h-16 w-16 text-gray-300" />
          <h1 className="mt-4 text-2xl font-bold text-gray-900">No File Uploaded</h1>
          <p className="mt-2 text-gray-600">
            Please upload an XML file first to start editing
          </p>
          <div className="mt-6">
            <a
              href="/upload"
              className="btn-primary"
            >
              Upload File
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Edit XML Form</h1>
        <p className="mt-2 text-gray-600">
          Use AI-powered natural language prompts to modify your form
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* File Status */}
        <div className="lg:col-span-1">
          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-semibold text-gray-900">Current File</h2>
            </div>
            <div className="card-content space-y-4">
              <div className="flex items-start space-x-3">
                <FileText className="h-5 w-5 text-gray-400 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {status.original_file?.split(/[/\\]/).pop() || 'Unknown file'}
                  </p>
                  <p className="text-xs text-gray-500">Original file</p>
                </div>
              </div>

              {status.has_modifications && (
                <div className="flex items-start space-x-3">
                  <Edit3 className="h-5 w-5 text-green-500 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {status.modified_file?.split(/[/\\]/).pop() || 'Modified version'}
                    </p>
                    <p className="text-xs text-gray-500">Modified version</p>
                  </div>
                </div>
              )}

              <div className="pt-4 border-t space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Worksheets:</span>
                  <span className="font-medium">{status.worksheets?.length || 0}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Total edits:</span>
                  <span className="font-medium">{status.total_edits || 0}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Has changes:</span>
                  <span className={`font-medium ${status.has_modifications ? 'text-green-600' : 'text-gray-600'}`}>
                    {status.has_modifications ? 'Yes' : 'No'}
                  </span>
                </div>
              </div>

              <div className="pt-4 border-t">
                <button
                  onClick={handleExport}
                  disabled={!status.has_modifications || exporting}
                  className={`w-full btn-primary ${(!status.has_modifications || exporting) ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <Download className="h-4 w-4 mr-2" />
                  {exporting ? 'Exporting...' : 'Export XML'}
                </button>
                {!status.has_modifications && (
                  <p className="text-xs text-gray-500 mt-2">Run AI edits to enable export.</p>
                )}
              </div>
            </div>
          </div>

          {/* Worksheets */}
          {status.worksheets && status.worksheets.length > 0 && (
            <div className="card mt-6">
              <div className="card-header">
                <h2 className="text-lg font-semibold text-gray-900">Worksheets</h2>
              </div>
              <div className="card-content">
                <div className="space-y-2">
                  {status.worksheets.map((worksheet, index) => (
                    <div key={index} className="flex items-center space-x-2">
                      <FileText className="h-4 w-4 text-gray-400" />
                      <span className="text-sm text-gray-700 capitalize">{worksheet}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* AI Editor */}
        <div className="lg:col-span-2">
          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-semibold text-gray-900">AI Editor</h2>
              <p className="text-sm text-gray-600">
                Describe what you want to change in natural language
              </p>
            </div>
            <div className="card-content">
              <form onSubmit={handleAIEdit} className="space-y-4">
                <div>
                  <label htmlFor="target-sheet" className="block text-sm font-medium text-gray-700 mb-1">
                    Target Worksheet (optional)
                  </label>
                  <select
                    id="target-sheet"
                    value={targetSheet}
                    onChange={(e) => setTargetSheet(e.target.value)}
                    className="input"
                  >
                    <option value="">All worksheets</option>
                    {status.worksheets?.map((worksheet, index) => (
                      <option key={index} value={worksheet} className="capitalize">
                        {worksheet}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="edit-prompt" className="block text-sm font-medium text-gray-700 mb-1">
                    Edit Instructions
                  </label>
                  <textarea
                    id="edit-prompt"
                    value={editPrompt}
                    onChange={(e) => setEditPrompt(e.target.value)}
                    rows={4}
                    className="input resize-none"
                    placeholder="Example: Add choices A, B, C to list MYLIST&#10;Example: Remove all fields containing 'test' from survey sheet&#10;Example: Add a new field called 'inspector_name' with type text"
                  />
                </div>

                <button
                  type="submit"
                  disabled={!editPrompt.trim() || editing}
                  className="btn-primary"
                >
                  <Send className="h-4 w-4 mr-2" />
                  {editing ? 'Processing...' : 'Apply Changes'}
                </button>
              </form>

              <div className="mt-6 p-4 bg-blue-50 rounded-lg">
                <h3 className="text-sm font-medium text-blue-900 mb-2">💡 AI Editor Tips</h3>
                <ul className="text-sm text-blue-800 space-y-1">
                  <li>• Be specific about what you want to change</li>
                  <li>• Mention the worksheet name if targeting a specific sheet</li>
                  <li>• Use field names exactly as they appear in your form</li>
                  <li>• You can add, remove, or modify fields and choices</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Edit History */}
          {status.edit_history && status.edit_history.length > 0 && (
            <div className="card mt-6">
              <div className="card-header">
                <h2 className="text-lg font-semibold text-gray-900">Recent Edits</h2>
              </div>
              <div className="card-content">
                <div className="space-y-4">
                  {status.edit_history.slice().reverse().map((edit, index) => (
                    <div key={index} className="border-l-4 border-gray-200 pl-4">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <p className="text-sm text-gray-900">{edit.prompt}</p>
                          {edit.target_sheet && (
                            <p className="text-xs text-gray-500 mt-1">
                              Target: {edit.target_sheet}
                            </p>
                          )}
                          <div className="flex items-center space-x-4 mt-2">
                            <div className="flex items-center space-x-1">
                              <Clock className="h-3 w-3 text-gray-400" />
                              <span className="text-xs text-gray-500">
                                {new Date(edit.timestamp).toLocaleString()}
                              </span>
                            </div>
                            {edit.user && (
                              <div className="flex items-center space-x-1">
                                <User className="h-3 w-3 text-gray-400" />
                                <span className="text-xs text-gray-500">{edit.user}</span>
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="ml-4">
                          {edit.success ? (
                            <CheckCircle className="h-5 w-5 text-green-500" />
                          ) : (
                            <AlertCircle className="h-5 w-5 text-red-500" />
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Files;
