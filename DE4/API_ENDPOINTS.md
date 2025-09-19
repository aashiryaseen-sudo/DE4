# DE4 Forms Platform API Endpoints

## Overview

The DE4 Forms Platform provides a comprehensive REST API for managing XML-based XLSForms with user authentication, database integration, and AI-powered editing capabilities.

## Base URL
```
http://localhost:8000
```

## Authentication

Most endpoints require authentication via session tokens. Include the token in the `Authorization` header:
```
Authorization: Bearer <session_token>
```

## Endpoints

### 🏥 System Health

#### GET `/api/health`
Get system health status and database connectivity.

**Response:**
```json
{
  "status": "healthy",
  "database_status": "connected",
  "timestamp": "2024-01-01T12:00:00Z",
  "stats": {
    "users": 5,
    "active_sessions": 3,
    "master_forms": 12,
    "active_master_forms": 10,
    "form_versions": 25,
    "customization_requests": 8,
    "pending_requests": 2,
    "form_operations": 150
  },
  "message": "All systems operational"
}
```

### 👤 User Management

#### POST `/api/users/register`
Create a new user account.

**Request Body:**
```json
{
  "username": "johndoe",
  "email": "john@example.com",
  "password": "securepass123",
  "full_name": "John Doe",
  "company": "Example Corp",
  "department": "Engineering",
  "phone": "+1234567890"
}
```

**Response:**
```json
{
  "id": 123,
  "username": "johndoe",
  "email": "john@example.com",
  "full_name": "John Doe",
  "role": "viewer",
  "company": "Example Corp",
  "department": "Engineering",
  "is_active": true,
  "is_verified": false,
  "created_at": "2024-01-01T12:00:00Z"
}
```

#### POST `/api/auth/login`
Authenticate user and create session.

**Request Body:**
```json
{
  "username": "johndoe",
  "password": "securepass123"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Login successful",
  "user": {
    "id": 123,
    "username": "johndoe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "role": "viewer",
    "company": "Example Corp",
    "department": "Engineering",
    "is_active": true,
    "is_verified": false,
    "created_at": "2024-01-01T12:00:00Z"
  },
  "session_token": "uuid-session-token-here",
  "expires_at": "2024-01-02T12:00:00Z"
}
```

#### POST `/api/auth/logout`
Logout user and terminate current session.

**Headers:** `Authorization: Bearer <session_token>`

**Response:**
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

### 📄 File Operations

#### POST `/api/upload`
Upload and analyze XML/XLS file.

**Headers:** `Authorization: Bearer <session_token>`

**Request:** Multipart form data with file

**Response:**
```json
{
  "success": true,
  "message": "File uploaded and analyzed successfully",
  "file_path": "uploads/form.xml",
  "worksheets": ["survey", "choices", "settings"],
  "total_sheets": 3,
  "analysis": {
    "worksheets": {
      "survey": {...},
      "choices": {...},
      "settings": {...}
    }
  },
  "uploaded_by": "johndoe"
}
```

#### POST `/api/ai-edit`
AI-powered editing with natural language prompts.

**Headers:** `Authorization: Bearer <session_token>`

**Request Body:**
```json
{
  "prompt": "Add choices A, B, C to list MYLIST",
  "target_sheet": "choices"
}
```

**Response:**
```json
{
  "success": true,
  "prompt": "Add choices A, B, C to list MYLIST",
  "target_sheet": "choices",
  "agent_response": "Successfully added choices to MYLIST...",
  "tool_calls_made": 2,
  "summary": "Changes applied successfully",
  "modified_file": "modified_form_20240101_120000.xml",
  "changes_applied": true,
  "edited_by": "johndoe"
}
```

#### GET `/api/export/xml`
Download the modified XML file.

**Headers:** `Authorization: Bearer <session_token>`

**Response:** File download with headers:
- `X-File-Type`: "modified" or "original"
- `X-Has-Modifications`: "true" or "false"
- `X-Exported-By`: username

#### GET `/api/status`
Get current system status (legacy endpoint for file operations).

**Response:**
```json
{
  "has_file_uploaded": true,
  "original_file": "uploads/form.xml",
  "modified_file": "modified_form_20240101_120000.xml",
  "has_modifications": true,
  "worksheets": ["survey", "choices", "settings"],
  "total_edits": 5,
  "edit_history": [...],
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 👨‍💼 Admin Operations

#### GET `/api/admin/dashboard`
Get comprehensive admin dashboard data.

**Headers:** `Authorization: Bearer <admin_session_token>`

**Response:**
```json
{
  "master_forms": [
    {
      "id": 1,
      "form_id": "form_abc123",
      "name": "HVAC Maintenance Form",
      "description": "Standard HVAC maintenance checklist",
      "current_version": "1.2",
      "version_count": 3,
      "form_type": "HVAC",
      "equipment_types": ["Boiler", "Chiller", "Pump"],
      "tags": ["maintenance", "hvac"],
      "is_active": true,
      "usage_count": 25,
      "field_count": 45,
      "section_count": 6,
      "file_size": 15420,
      "created_at": "2024-01-01T10:00:00Z",
      "updated_at": "2024-01-01T11:30:00Z"
    }
  ],
  "form_versions": [
    {
      "id": 1,
      "master_form_id": 1,
      "version": "1.2",
      "is_current": true,
      "is_published": true,
      "file_size": 15420,
      "created_by": 1,
      "change_summary": "Added new equipment fields",
      "created_at": "2024-01-01T11:30:00Z",
      "master_form_name": "HVAC Maintenance Form"
    }
  ],
  "customization_requests": [
    {
      "id": 1,
      "request_id": "req_xyz789",
      "client_name": "ABC Company",
      "form_title": "Custom HVAC Form",
      "master_form_id": 1,
      "status": "pending",
      "priority": 2,
      "created_by": 2,
      "assigned_to": null,
      "processing_time_seconds": null,
      "quality_score": null,
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-01T12:00:00Z",
      "master_form_name": "HVAC Maintenance Form",
      "created_by_username": "johndoe"
    }
  ],
  "recent_operations": [
    {
      "id": 1,
      "operation_id": "op_def456",
      "operation_type": "create",
      "operation_description": "User account created: johndoe",
      "target_type": "user",
      "target_id": "123",
      "target_name": "johndoe",
      "user_id": 123,
      "success": true,
      "error_message": null,
      "execution_time_ms": 150,
      "started_at": "2024-01-01T11:45:00Z",
      "completed_at": "2024-01-01T11:45:00Z",
      "username": "johndoe"
    }
  ],
  "active_sessions": [
    {
      "id": 1,
      "user_id": 123,
      "session_token": "uuid-tok...",
      "ip_address": "192.168.1.100",
      "status": "active",
      "expires_at": "2024-01-02T12:00:00Z",
      "last_activity": "2024-01-01T12:00:00Z",
      "created_at": "2024-01-01T11:30:00Z",
      "username": "johndoe",
      "user_role": "viewer"
    }
  ],
  "stats": {
    "users": 5,
    "active_sessions": 3,
    "master_forms": 12,
    "active_master_forms": 10,
    "form_versions": 25,
    "customization_requests": 8,
    "pending_requests": 2,
    "form_operations": 150,
    "total_file_size": 2048576,
    "avg_processing_time": 45.2,
    "successful_operations": 142,
    "failed_operations": 8
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

## Error Responses

All endpoints return consistent error responses:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- `200`: Success
- `400`: Bad Request (validation errors)
- `401`: Unauthorized (invalid/missing session token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found
- `422`: Unprocessable Entity (business logic errors)
- `500`: Internal Server Error

## Database Integration

All operations are logged in the audit trail (`form_operations` table) with:
- Operation type (CREATE, READ, UPDATE, DELETE, CLONE, DEPLOY)
- User information
- Target details
- Success/failure status
- Before/after data where applicable
- Performance metrics

## Session Management

- Sessions expire after 24 hours by default
- Multiple concurrent sessions per user are supported
- Expired sessions are automatically cleaned up
- Session activity is tracked and logged

## Security Features

- Password hashing (SHA-256, upgrade to bcrypt recommended for production)
- Session-based authentication
- Role-based access control (ADMIN, MANAGER, EDITOR, VIEWER)
- Comprehensive audit logging
- Input validation and sanitization

## Getting Started

1. Start the server: `uvicorn main:app --reload`
2. Initialize database: Database auto-initializes on startup
3. Default admin credentials: `admin` / `admin123`
4. Test endpoints: `python test_endpoints.py`

## Development Notes

- Database supports both SQLite (development) and PostgreSQL (production)
- All endpoints support async operations
- Comprehensive logging and error handling
- OpenAPI documentation available at `/docs`
