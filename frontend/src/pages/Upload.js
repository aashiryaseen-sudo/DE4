import React, { useState, useRef } from 'react';
import { fileAPI } from '../services/api';
import { Upload, FileText, AlertCircle, CheckCircle, X } from 'lucide-react';
import toast from 'react-hot-toast';

const UploadPage = () => {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileSelect = (selectedFile) => {
    if (selectedFile && (selectedFile.name.endsWith('.xml') || selectedFile.name.endsWith('.xls'))) {
      setFile(selectedFile);
      setUploadResult(null);
    } else {
      toast.error('Please select a valid XML or XLS file');
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    handleFileSelect(droppedFile);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleFileInputChange = (e) => {
    const selectedFile = e.target.files[0];
    handleFileSelect(selectedFile);
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    try {
      const response = await fileAPI.upload(file);
      setUploadResult(response.data);
      toast.success('File uploaded and analyzed successfully!');
    } catch (error) {
      console.error('Upload failed:', error);
      toast.error('Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const removeFile = () => {
    setFile(null);
    setUploadResult(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Upload XML Form</h1>
        <p className="mt-2 text-gray-600">
          Upload your XLSForm XML file to start editing with AI assistance
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Upload Section */}
        <div className="space-y-6">
          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-semibold text-gray-900">Select File</h2>
            </div>
            <div className="card-content">
              <div
                className={`relative border-2 border-dashed rounded-lg p-6 transition-colors ${
                  dragOver
                    ? 'border-primary-400 bg-primary-50'
                    : 'border-gray-300 hover:border-gray-400'
                }`}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
              >
                <div className="text-center">
                  <Upload className="mx-auto h-12 w-12 text-gray-400" />
                  <div className="mt-4">
                    <label htmlFor="file-upload" className="cursor-pointer">
                      <span className="text-primary-600 hover:text-primary-500 font-medium">
                        Click to upload
                      </span>
                      <span className="text-gray-500"> or drag and drop</span>
                    </label>
                    <input
                      id="file-upload"
                      ref={fileInputRef}
                      type="file"
                      className="sr-only"
                      accept=".xml,.xls"
                      onChange={handleFileInputChange}
                    />
                  </div>
                  <p className="text-sm text-gray-500 mt-2">
                    XML or XLS files only
                  </p>
                </div>
              </div>

              {file && (
                <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <FileText className="h-5 w-5 text-gray-400" />
                      <div>
                        <p className="text-sm font-medium text-gray-900">{file.name}</p>
                        <p className="text-sm text-gray-500">
                          {(file.size / 1024).toFixed(1)} KB
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={removeFile}
                      className="text-gray-400 hover:text-gray-600"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              )}

              <div className="mt-6">
                <button
                  onClick={handleUpload}
                  disabled={!file || uploading}
                  className="btn-primary w-full"
                >
                  {uploading ? (
                    <div className="flex items-center justify-center">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Uploading...
                    </div>
                  ) : (
                    'Upload & Analyze'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Results Section */}
        <div className="space-y-6">
          {uploadResult && (
            <div className="card">
              <div className="card-header">
                <div className="flex items-center space-x-2">
                  <CheckCircle className="h-5 w-5 text-green-500" />
                  <h2 className="text-lg font-semibold text-gray-900">Analysis Complete</h2>
                </div>
              </div>
              <div className="card-content space-y-4">
                <div>
                  <h3 className="text-sm font-medium text-gray-900 mb-2">File Information</h3>
                  <div className="bg-gray-50 rounded-lg p-3 space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">Uploaded by:</span>
                      <span className="font-medium">{uploadResult.uploaded_by}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">Worksheets:</span>
                      <span className="font-medium">{uploadResult.total_sheets}</span>
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium text-gray-900 mb-2">Worksheets Found</h3>
                  <div className="space-y-2">
                    {uploadResult.worksheets.map((worksheet, index) => (
                      <div key={index} className="flex items-center space-x-2">
                        <FileText className="h-4 w-4 text-gray-400" />
                        <span className="text-sm text-gray-700 capitalize">{worksheet}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-4 border-t">
                  <p className="text-sm text-green-600 font-medium">
                    ✓ File ready for AI editing
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    You can now use natural language prompts to modify your form
                  </p>
                </div>
              </div>
            </div>
          )}

          {!uploadResult && (
            <div className="card">
              <div className="card-content">
                <div className="text-center py-8">
                  <AlertCircle className="mx-auto h-12 w-12 text-gray-300" />
                  <h3 className="mt-4 text-lg font-medium text-gray-900">
                    No file uploaded yet
                  </h3>
                  <p className="mt-2 text-sm text-gray-500">
                    Upload a file to see the analysis results here
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default UploadPage;
