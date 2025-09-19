import json
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, Depends, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, validator
from typing import Union

from langgraph_proper_agent import create_proper_xlsform_agent
from database import (
    get_database_session, get_current_user, get_current_active_user, 
    get_admin_user, require_editor_user, initialize_database, db_manager
)
from database_manager import get_user_manager, get_form_manager, get_operation_logger
from database_schema import User, UserRole, SessionStatus, RequestStatus, OperationType
from sqlalchemy.orm import Session
from models import (
    Choice,
    ChoiceCreate,
    ChoiceList,
    ChoiceUpdate,
    FieldTypeInfo,
    FormSettings,
    FormSettingsUpdate,
    PaginationParams,
    SurveyField,
    SurveyFieldCreate,
    SurveyFieldResponse,
    SurveyFieldUpdate,
    SurveyStats,
    XLSFormData,
    XLSFormStats,
)
from xml_parser import create_xml_editor
import uuid
from pathlib import Path

app = FastAPI(
    title="DE4 Forms Platform API",
    description="AI-powered XLSForm platform with user management and customization",
    version="2.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and cleanup on startup"""
    # Print DB debug summary and connection status at startup
    try:
        from database import db_manager as dm
        summary = dm.debug_summary()
        print("DB Config:", summary)
        conn_test = dm.test_connection()
        print("DB Connection Test:", {k: v for k, v in conn_test.items() if k != 'database_url'})
    except Exception as e:
        print("DB debug failed:", str(e))

    success = initialize_database()
    if not success:
        print("Warning: Database initialization failed")
    
    # Cleanup expired sessions
    try:
        cleaned = db_manager.cleanup_expired_sessions()
        print(f"Cleaned up {cleaned} expired sessions")
    except Exception as e:
        print(f"Session cleanup error: {e}")

# =============== PYDANTIC MODELS ===============

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str = ""
    company: str = ""
    department: str = ""
    phone: str = ""
    
    @validator('username')
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters long')
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username can only contain letters, numbers, hyphens, and underscores')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters long')
        return v

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    company: str
    department: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    message: str
    user: UserResponse
    session_token: str
    expires_at: datetime

class HealthResponse(BaseModel):
    status: str
    database_status: str
    timestamp: datetime
    stats: Dict[str, int]
    message: str

class AdminDashboardResponse(BaseModel):
    # Form data
    master_forms: List[Dict[str, Any]]
    form_versions: List[Dict[str, Any]]
    
    # Request data  
    customization_requests: List[Dict[str, Any]]
    
    # Operations and sessions
    recent_operations: List[Dict[str, Any]]
    active_sessions: List[Dict[str, Any]]
    
    # Statistics
    stats: Dict[str, int]
    timestamp: datetime

class UpdateUserRoleRequest(BaseModel):
    role: str

# CustomizationRequest removed - using user prompts instead

# Global storage for current form
current_form_analysis: Optional[Dict[str, Any]] = None
current_uploaded_file: Optional[str] = None
current_modified_file: Optional[str] = None
edit_history: List[Dict[str, Any]] = []

# =============== USER MANAGEMENT ENDPOINTS ===============

@app.post("/api/users/register", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_database_session)
):
    """
    Create a new user account
    
    - **username**: Unique username (3+ chars, alphanumeric with - and _)
    - **email**: Valid email address
    - **password**: Password (6+ characters)
    - **full_name**: User's full name (optional)
    - **company**: Company name (optional)
    - **department**: Department (optional)
    - **phone**: Phone number (optional)
    """
    try:
        user_manager = get_user_manager()
        operation_logger = get_operation_logger()
        
        # Create user with EDITOR role by default
        new_user = user_manager.create_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name,
            role=UserRole.EDITOR,
            company=user_data.company,
            department=user_data.department,
            phone=user_data.phone,
            is_active=True,
            is_verified=False  # Require email verification in production
        )
        
        if not new_user:
            # Distinguish duplicate from other DB errors to avoid misleading 400s
            from database_schema import User as DBUser
            duplicate = db.query(DBUser).filter(
                (DBUser.username == user_data.username) | (DBUser.email == user_data.email)
            ).first()
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username or email already exists"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="User creation failed due to an internal error"
                )
        
        # Log user creation operation
        operation_logger.log_operation(
            operation_type=OperationType.CREATE,
            description=f"User account created: {user_data.username}",
            target_type="user",
            target_id=str(new_user.id),
            target_name=new_user.username,
            user_id=new_user.id,
            success=True
        )
        
        return UserResponse(
            id=new_user.id,
            username=new_user.username,
            email=new_user.email,
            full_name=new_user.full_name,
            role=(new_user.role.value if hasattr(new_user.role, 'value') else new_user.role),
            company=new_user.company or "",
            department=new_user.department or "",
            is_active=new_user.is_active,
            is_verified=new_user.is_verified,
            created_at=new_user.created_at
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        # Propagate HTTPExceptions (e.g., 400 duplicate user) without wrapping as 500
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User creation failed: {str(e)}"
        )

@app.post("/api/auth/login", response_model=LoginResponse)
async def login_user(
    login_data: LoginRequest,
    db: Session = Depends(get_database_session)
):
    """
    Authenticate user and create session
    
    Returns session token for authenticated requests
    """
    try:
        user_manager = get_user_manager()
        operation_logger = get_operation_logger()
        
        # Authenticate user
        user = user_manager.authenticate_user(login_data.username, login_data.password)
        
        if not user:
            # Log failed login attempt
            operation_logger.log_operation(
                operation_type=OperationType.READ,
                description=f"Failed login attempt for username: {login_data.username}",
                target_type="user",
                target_name=login_data.username,
                success=False
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        # Create session
        session = user_manager.create_session(
            user_id=user.id,
            expires_hours=24
        )
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create session"
            )
        
        # Log successful login
        operation_logger.log_operation(
            operation_type=OperationType.READ,
            description=f"User logged in: {user.username}",
            target_type="user",
            target_id=str(user.id),
            target_name=user.username,
            user_id=user.id,
            success=True
        )
        
        return LoginResponse(
            success=True,
            message="Login successful",
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                role=(user.role.value if hasattr(user.role, 'value') else user.role),
                company=user.company or "",
                department=user.department or "",
                is_active=user.is_active,
                is_verified=user.is_verified,
                created_at=user.created_at
            ),
            session_token=session.session_token,
            expires_at=session.expires_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@app.post("/api/auth/logout")
async def logout_user(
    authorization: Optional[str] = None,
):
    """
    Idempotent logout:
    - If a valid Bearer token is provided, terminate that session.
    - If token is missing/invalid/expired, still return success.
    """
    try:
        from database_schema import UserSession
        terminated = False
        token_value: Optional[str] = None
        if authorization:
            try:
                scheme, _, token = authorization.partition(" ")
                if scheme.lower() == "bearer" and token:
                    token_value = token.strip()
            except Exception:
                token_value = None
        if token_value:
            try:
                with db_manager.get_session() as session:
                    user_session = session.query(UserSession).filter(
                        UserSession.session_token == token_value,
                        UserSession.status == SessionStatus.ACTIVE
                    ).first()
                    if user_session:
                        user_session.status = SessionStatus.TERMINATED
                        user_session.terminated_at = datetime.utcnow()
                        session.commit()
                        terminated = True
            except Exception:
                # swallow errors to keep idempotent behavior
                pass
        # Always return success
        get_operation_logger().log_operation(
            operation_type=OperationType.UPDATE,
            description="User logout (idempotent)",
            target_type="user_session",
            success=True,
            after_data={"terminated": terminated}
        )
        return {"success": True, "message": "Logged out successfully"}
    except Exception:
        return {"success": True, "message": "Logged out successfully"}

# =============== SYSTEM STATUS ENDPOINTS ===============

@app.get("/api/health", response_model=HealthResponse)
async def get_system_health():
    """
    Get system health status including database connectivity
    
    Returns overall system status, database health, and statistics
    """
    try:
        # Get database health
        health_check = db_manager.health_check()
        
        if health_check["status"] == "healthy":
            return HealthResponse(
                status="healthy",
                database_status="connected",
                timestamp=datetime.utcnow(),
                stats=health_check["stats"],
                message="All systems operational"
            )
        else:
            return HealthResponse(
                status="degraded",
                database_status="error",
                timestamp=datetime.utcnow(),
                stats={},
                message=f"Database error: {health_check.get('error', 'Unknown error')}"
            )
            
    except Exception as e:
        return HealthResponse(
            status="error",
            database_status="disconnected",
            timestamp=datetime.utcnow(),
            stats={},
            message=f"System error: {str(e)}"
        )

# =============== ADMIN ENDPOINTS ===============
@app.get("/api/debug/db")
async def debug_database(
    admin_user: User = Depends(get_admin_user)
):
    """Admin-only DB diagnostics: connection test and health stats"""
    try:
        from database import db_manager as dm
        test = dm.test_connection()
        health = dm.health_check()
        return {
            "test": test,
            "health": health,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB debug failed: {str(e)}")

@app.get("/api/admin/dashboard", response_model=AdminDashboardResponse)
async def get_admin_dashboard(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_database_session)
):
    """
    Get comprehensive admin dashboard data
    
    Returns:
    - All master forms with metadata
    - Form version history
    - Customization requests
    - Recent operations (audit log)
    - Active user sessions
    - System statistics
    
    Requires admin privileges.
    """
    try:
        print(f"🔍 Admin dashboard accessed by: {admin_user.username}")
        operation_logger = get_operation_logger()
        
        # Use the passed db session instead of creating a new one
        session = db
        from database_schema import (
            MasterForm, FormVersion, UserFormSession,
            FormOperation, UserSession, User
        )
        from sqlalchemy import func
            
        # Get master forms with metadata
        master_forms_query = session.query(MasterForm).order_by(MasterForm.created_at.desc()).limit(50)
        master_forms = []
        print(f"📊 Found {master_forms_query.count()} master forms")
        for form in master_forms_query:
            master_forms.append({
                "id": form.id,
                "form_id": form.form_id,
                "name": form.name,
                "description": form.description,
                "current_version": form.current_version,
                "version_count": form.version_count,
                "form_type": form.form_type,
                "equipment_types": form.equipment_types,
                "tags": form.tags,
                "is_active": form.is_active,
                "usage_count": form.usage_count,
                "field_count": form.field_count,
                "section_count": form.section_count,
                "file_size": form.file_size,
                "created_at": form.created_at.isoformat(),
                "updated_at": form.updated_at.isoformat()
            })
        
        # Get form versions
        versions_query = session.query(FormVersion).order_by(FormVersion.created_at.desc()).limit(100)
        form_versions = []
        for version in versions_query:
            form_versions.append({
                "id": version.id,
                "master_form_id": version.master_form_id,
                "version": version.version,
                "is_current": version.is_current,
                "is_published": version.is_published,
                "file_size": version.file_size,
                "created_by": version.created_by,
                "change_summary": version.change_summary,
                "created_at": version.created_at.isoformat(),
                "master_form_name": version.master_form.name if version.master_form else None
            })
        
        # Get user prompts from edit history as "requests"
        user_form_sessions = session.query(UserFormSession).all()
        all_prompts = []
        for session_obj in user_form_sessions:
            if session_obj.edit_history_json:
                for edit in session_obj.edit_history_json:
                    all_prompts.append({
                        "id": f"{session_obj.id}_{len(all_prompts)}",
                        "prompt": edit.get("prompt", ""),
                        "target_sheet": edit.get("target_sheet"),
                        "success": edit.get("success", False),
                        "timestamp": edit.get("timestamp"),
                        "user_id": session_obj.user_id,
                        "status": "completed" if edit.get("success", False) else "failed"
                    })
        
        # Sort by timestamp (most recent first)
        all_prompts.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        customization_requests = all_prompts[:100]  # Limit to 100 most recent
        print(f"📋 Found {len(customization_requests)} user prompts (requests)")
        
        # Get recent operations (audit log)
        operations_query = session.query(FormOperation).order_by(FormOperation.started_at.desc()).limit(200)
        recent_operations = []
        print(f"🔧 Found {operations_query.count()} operations")
        for op in operations_query:
            recent_operations.append({
                "id": op.id,
                "operation_id": op.operation_id,
                "operation_type": op.operation_type.value,
                "operation_description": op.operation_description,
                "target_type": op.target_type,
                "target_id": op.target_id,
                "target_name": op.target_name,
                "user_id": op.user_id,
                "success": op.success,
                "error_message": op.error_message,
                "execution_time_ms": op.execution_time_ms,
                "started_at": op.started_at.isoformat(),
                "completed_at": op.completed_at.isoformat() if op.completed_at else None,
                "username": op.user.username if op.user else None
            })
        
        # Get active sessions
        sessions_query = session.query(UserSession).filter(
            UserSession.status == SessionStatus.ACTIVE
        ).order_by(UserSession.last_activity.desc()).limit(100)
        active_sessions = []
        for sess in sessions_query:
            active_sessions.append({
                "id": sess.id,
                "user_id": sess.user_id,
                "session_token": sess.session_token[:8] + "...",  # Truncate for security
                "ip_address": str(sess.ip_address) if sess.ip_address else None,
                "status": sess.status.value,
                "expires_at": sess.expires_at.isoformat(),
                "last_activity": sess.last_activity.isoformat(),
                "created_at": sess.created_at.isoformat(),
                "username": sess.user.username if sess.user else None,
                "user_role": sess.user.role.value if sess.user else None
            })
        
        # Get comprehensive statistics
        from database_schema import get_database_stats
        stats = get_database_stats(session)
        
        # Add additional stats
        stats.update({
            "total_file_size": session.query(func.sum(MasterForm.file_size)).filter(MasterForm.file_size.isnot(None)).scalar() or 0,
            "avg_processing_time": 0,  # Not applicable for user prompts
            "successful_operations": session.query(FormOperation).filter(FormOperation.success == True).count(),
            "failed_operations": session.query(FormOperation).filter(FormOperation.success == False).count()
        })
        
        # Log admin dashboard access
        operation_logger.log_operation(
            operation_type=OperationType.READ,
            description=f"Admin dashboard accessed by: {admin_user.username}",
            target_type="admin_dashboard",
            user_id=admin_user.id,
            success=True
        )
        
        return AdminDashboardResponse(
            master_forms=master_forms,
            form_versions=form_versions,
            customization_requests=customization_requests,
            recent_operations=recent_operations,
            active_sessions=active_sessions,
            stats=stats,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch admin dashboard data: {str(e)}"
        )

# =============== CORE API ENDPOINTS ===============

@app.put("/api/admin/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    payload: UpdateUserRoleRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_database_session)
):
    """Promote/demote users between admin and editor. Admin-only.
    Guard: cannot demote the last remaining admin.
    """
    try:
        role_target = payload.role.lower().strip()
        if role_target not in {"admin", "editor"}:
            raise HTTPException(status_code=400, detail="Role must be 'admin' or 'editor'")

        from database_schema import User as DBUser, UserRole as UR
        user = db.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        current_role = user.role.value if hasattr(user.role, 'value') else user.role
        if current_role == role_target:
            return {"success": True, "message": "No change", "user_id": user_id, "role": current_role}

        # If demoting from admin, ensure there will be at least one admin left
        if current_role == "admin" and role_target != "admin":
            remaining_admins = db.query(DBUser).filter(DBUser.role == UR.ADMIN.value, DBUser.id != user_id).count()
            if remaining_admins == 0:
                raise HTTPException(status_code=400, detail="Cannot demote the last remaining admin")

        # Apply role change
        user.role = role_target
        db.commit()
        db.refresh(user)

        # Audit log
        operation_logger = get_operation_logger()
        operation_logger.log_operation(
            operation_type=OperationType.UPDATE,
            description=f"Role changed to {role_target} for user_id={user_id}",
            target_type="user",
            target_id=str(user_id),
            user_id=admin_user.id,
            success=True,
            before_data={"previous_role": current_role},
            after_data={"new_role": role_target}
        )

        return {"success": True, "user_id": user_id, "role": role_target}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update role: {str(e)}")

@app.get("/api/admin/users")
async def list_users(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_database_session)
):
    """List users for admin management (id, username, email, role, is_active, created_at)."""
    try:
        from database_schema import User as DBUser
        users = db.query(DBUser).order_by(DBUser.created_at.desc()).limit(500).all()
        def serialize(u):
            role_value = u.role.value if hasattr(u.role, 'value') else u.role
            return {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "full_name": u.full_name,
                "role": role_value,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
        return {"users": [serialize(u) for u in users]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")

# Customization request endpoint removed - using user prompts instead

@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_editor_user),
    db: Session = Depends(get_database_session)
):
    """
    Upload and analyze XML file

    This endpoint:
    1. Accepts XML/XLS file upload
    2. Analyzes all worksheets automatically
    3. Stores analysis for AI editing
    """
    if not file.filename.lower().endswith((".xml", ".xls")):
        raise HTTPException(status_code=400, detail="Only XML and XLS files are supported")

    # Create per-user working session and save under uploads/{user_id}/{session_uuid}/
    session_uuid = str(uuid.uuid4())
    base_dir = Path("uploads") / str(current_user.id) / session_uuid
    base_dir.mkdir(parents=True, exist_ok=True)
    file_path = base_dir / file.filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        # Analyze the uploaded file using the XML editor utilities
        editor = create_xml_editor(str(file_path))
        # Build a lightweight analysis: worksheets and headers
        worksheets_info: Dict[str, Any] = {}
        try:
            # Access internal helpers in a safe way
            all_ws = editor._iter_worksheets() if hasattr(editor, "_iter_worksheets") else []
            for ws in all_ws:
                # Worksheet name attribute
                name_attr = ws.get("{urn:schemas-microsoft-com:office:spreadsheet}Name") or ""
                table = editor.find_table_in_worksheet(ws) if hasattr(editor, "find_table_in_worksheet") else None
                headers = editor.get_headers(table) if table is not None and hasattr(editor, "get_headers") else []
                worksheets_info[name_attr] = {
                    "headers": headers,
                    "row_count": int(table.get("{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount", "0")) if table is not None else 0,
                }
        except Exception:
            worksheets_info = {}

        form_analysis: Dict[str, Any] = {
            "worksheets": worksheets_info,
            "detected_choice_sheets": editor.detect_choice_worksheets() if hasattr(editor, "detect_choice_worksheets") else [],
        }

        # Persist user form session
        from database_schema import UserFormSession, FormWorkStatus
        user_form_session = UserFormSession(
            id=session_uuid,
            user_id=current_user.id,
            status=FormWorkStatus.ACTIVE.value,
            original_file_path=str(file_path),
            modified_file_path=None,
            analysis_json=form_analysis,
            edit_history_json=[],
        )
        db.add(user_form_session)
        db.commit()

        # Log file upload operation
        operation_logger = get_operation_logger()
        operation_logger.log_operation(
            operation_type=OperationType.CREATE,
            description=f"File uploaded: {file.filename}",
            target_type="file_upload",
            target_name=file.filename,
            user_id=current_user.id,
            success=True,
            after_data={
                "file_path": str(file_path),
                "file_size": len(content),
                "worksheets": list(form_analysis.get("worksheets", {}).keys()),
                "user_form_session_id": session_uuid,
            }
        )

        return {
            "success": True,
            "message": "File uploaded and analyzed successfully",
            "session_id": session_uuid,
            "file_path": str(file_path),
            "worksheets": list(form_analysis.get("worksheets", {}).keys()),
            "total_sheets": len(form_analysis.get("worksheets", {})),
            "analysis": form_analysis,
            "uploaded_by": current_user.username
        }

    except Exception as e:
        # Log failed upload
        operation_logger = get_operation_logger()
        operation_logger.log_operation(
            operation_type=OperationType.CREATE,
            description=f"File upload failed: {file.filename}",
            target_type="file_upload",
            target_name=file.filename,
            user_id=current_user.id,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Error analyzing uploaded form: {str(e)}")


@app.post("/api/ai-edit")
async def ai_edit_endpoint(
    prompt: str, 
    target_sheet: Optional[str] = None,
    current_user: User = Depends(require_editor_user),
    db: Session = Depends(get_database_session)
):
    """
    AI-powered editing with natural language prompts

    Examples:
    - "Add choices A, B, C to list MYLIST"
    - "Add row with data X, Y, Z to settings sheet"
    - "Remove all fields containing 'test' from survey sheet"

    The AI will:
    1. Parse your prompt into specific tasks
    2. Execute changes on the XML file
    3. Save a modified version with timestamp
    4. Return success/failure status
    """
    # Find the user's active form session
    from database_schema import UserFormSession, FormWorkStatus
    user_form_session = db.query(UserFormSession).filter(
        UserFormSession.user_id == current_user.id,
        UserFormSession.status == FormWorkStatus.ACTIVE.value
    ).order_by(UserFormSession.created_at.desc()).first()

    if not user_form_session or not user_form_session.original_file_path:
        raise HTTPException(status_code=400, detail="No form uploaded. Please upload an XML file first.")

    try:
        # Create LangGraph ReAct Agent
        # Choose working file: prefer last modified, else original
        working_file = user_form_session.modified_file_path or user_form_session.original_file_path
        agent = create_proper_xlsform_agent(working_file)

        # Add target sheet context to prompt if specified
        enhanced_prompt = prompt
        if target_sheet:
            enhanced_prompt = f"Focus on the '{target_sheet}' sheet. {prompt}"

        # Process the prompt using the ReAct agent
        print(f"🔍 Processing AI edit prompt: {enhanced_prompt}")
        result = await agent.process_prompt(enhanced_prompt)
        print(f"🔍 AI edit result: {result}")
        
        # Store the prompt in edit history
        edit_history = user_form_session.edit_history_json or []
        edit_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "prompt": prompt,
            "target_sheet": target_sheet,
            "success": result.get("success", False),
            "response": result.get("agent_response", "")
        })
        user_form_session.edit_history_json = edit_history

        if result["success"]:
            # Check for modified file
            modified_file_created = False
            # Locate latest modified file next to original
            import glob
            original_name = os.path.basename(user_form_session.original_file_path).replace(".xml", "")
            pattern = str(Path(user_form_session.original_file_path).parent / f"modified_{original_name}_*.xml")
            print(f"🔍 Looking for modified files with pattern: {pattern}")
            modified_files = glob.glob(pattern)
            print(f"🔍 Found {len(modified_files)} modified files: {modified_files}")
            latest_modified = None
            if modified_files:
                latest_modified = max(modified_files, key=os.path.getctime)
                modified_file_created = True
                print(f"✅ Using latest modified file: {latest_modified}")

            # Check for success indicators
            success_indicators = [
                "successfully added",
                "added choice option",
                "modified_file_path",
                "_modified.xml",
                "backup_created",
            ]

            response_lower = result["agent_response"].lower()
            actual_success = any(indicator.lower() in response_lower for indicator in success_indicators)

            # Require tool calls and modified file for success
            tool_calls_made = int(result.get("tool_calls_made", 0) or 0)
            agent_response = result.get("agent_response", "")
            
            # Check for successful task execution in the response
            has_successful_tasks = any([
                '"status": "completed"' in agent_response,
                '"completed_tasks"' in agent_response,
                'Successfully completed' in agent_response,
                '✅' in agent_response,
                '"execution_completed": true' in agent_response
            ])
            
            if tool_calls_made == 0 and not has_successful_tasks:
                raise HTTPException(status_code=422, detail="AI did not execute tools or no modified file was produced")

            # Persist changes to user form session
            history = user_form_session.edit_history_json or []
            # Determine if changes were actually applied
            changes_applied = modified_file_created or has_successful_tasks
            success = changes_applied or actual_success
            
            history.append({
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "target_sheet": target_sheet,
                "success": success,
                "changes_applied": changes_applied,
            })
            user_form_session.edit_history_json = history
            if latest_modified:
                # Store absolute path to ensure export can find it
                user_form_session.modified_file_path = os.path.abspath(latest_modified)
            elif has_successful_tasks:
                # Mark session as having modifications even if no file was created
                # This enables the export button for task-based edits
                user_form_session.modified_file_path = "task_based_edit"
            db.commit()

            # ================= Save form version to DB (full xml_content) =================
            try:
                from database_schema import MasterForm, FormVersion
                from database_manager import get_form_manager

                # Derive a stable form name from original filename (without extension)
                form_name = os.path.basename(user_form_session.original_file_path).replace(".xml", "")

                # Read modified XML content
                modified_path = user_form_session.modified_file_path or working_file
                xml_content = ""
                try:
                    with open(modified_path, "r", encoding="utf-8") as xf:
                        xml_content = xf.read()
                    print(f"📄 Read XML content: {len(xml_content)} characters from {modified_path}")
                except Exception as e:
                    print(f"❌ Failed to read XML content from {modified_path}: {str(e)}")
                    pass

                # Find or create master form
                master_form = db.query(MasterForm).filter(MasterForm.name == form_name).first()
                timestamp_version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")  # Full timestamp: YYYYMMDD_HHMMSS

                if not master_form:
                    # Restore previous behavior: create master form record when missing
                    form_manager = get_form_manager()
                    created = form_manager.create_master_form(
                        name=form_name,
                        version=timestamp_version,
                        xml_content=xml_content or "",
                        description=f"Auto-created from edits for {form_name}",
                        form_type="General",
                        equipment_types=[],
                        tags=[],
                        created_by=current_user.id
                    )
                    # Refresh from DB
                    master_form = db.query(MasterForm).filter(MasterForm.name == form_name).first()
                else:
                    # For existing master form, add a new version as a draft (do not mark as current)
                    new_version = FormVersion(
                        master_form_id=master_form.id,
                        version=f"{form_name}_{timestamp_version}",  # Descriptive version name
                        xml_content=xml_content or "",
                        xml_compressed=False,
                        form_structure=None,
                        field_names=None,
                        choice_lists=None,
                        file_path=modified_path,
                        file_size=os.path.getsize(modified_path) if os.path.exists(modified_path) else None,
                        file_checksum=None,
                        created_by=current_user.id,
                        change_summary=f"AI edit: {prompt[:50]}..." if len(prompt) > 50 else f"AI edit: {prompt}",
                        is_current=False,
                        is_published=False,
                    )
                    db.add(new_version)
                    db.commit()
                    print(f"✅ Saved version to DB: {new_version.version} with {len(xml_content)} characters")

            except Exception as e:
                print(f"❌ Failed to save version to DB: {str(e)}")
                # Rollback the transaction and start fresh
                db.rollback()
                # Non-fatal: version save failed shouldn't break edit response
                operation_logger = get_operation_logger()
                operation_logger.log_operation(
                    operation_type=OperationType.UPDATE,
                    description=f"Version save failed for {form_name}",
                    target_type="form_version",
                    target_name=form_name,
                    user_id=current_user.id,
                    success=False,
                    error_message=str(e)
                )

            # Log AI edit operation
            operation_logger = get_operation_logger()
            operation_logger.log_operation(
                operation_type=OperationType.UPDATE,
                description=f"AI edit applied: {prompt[:100]}",
                target_type="xml_file",
                target_name=current_uploaded_file,
                user_id=current_user.id,
                success=True,
                before_data={"prompt": prompt, "target_sheet": target_sheet},
                after_data={
                    "tool_calls_made": tool_calls_made,
                    "modified_file": user_form_session.modified_file_path,
                    "changes_applied": modified_file_created
                }
            )

            return {
                "success": True,
                "prompt": prompt,
                "target_sheet": target_sheet,
                "agent_response": result["agent_response"],
                "tool_calls_made": tool_calls_made,
                "summary": "Changes applied successfully",
                "modified_file": user_form_session.modified_file_path,
                "changes_applied": True,
                "edited_by": current_user.username
            }
        else:
            # Log failed AI edit
            operation_logger = get_operation_logger()
            operation_logger.log_operation(
                operation_type=OperationType.UPDATE,
                description=f"AI edit failed: {prompt[:100]}",
                target_type="xml_file",
                target_name=current_uploaded_file,
                user_id=current_user.id,
                success=False,
                error_message=result["error"]
            )
            return {"success": False, "error": result["error"], "prompt": prompt, "target_sheet": target_sheet}

    except Exception as e:
        # Log exception
        operation_logger = get_operation_logger()
        operation_logger.log_operation(
            operation_type=OperationType.UPDATE,
            description=f"AI edit exception: {prompt[:100]}",
            target_type="xml_file",
            target_name=current_uploaded_file,
            user_id=current_user.id,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=f"AI editing error: {str(e)}")


@app.get("/api/export/xml")
async def export_xml(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_database_session)
):
    """
    Download the modified XML file.
    Requires an edited file to exist; otherwise returns 400 instructing to run AI edit first.
    """
    from database_schema import UserFormSession, FormWorkStatus
    user_form_session = db.query(UserFormSession).filter(
        UserFormSession.user_id == current_user.id,
        UserFormSession.status == FormWorkStatus.ACTIVE.value
    ).order_by(UserFormSession.created_at.desc()).first()

    if not user_form_session or not user_form_session.original_file_path:
        raise HTTPException(status_code=400, detail="No form uploaded. Please upload an XML file first.")

    # Require that an edited file exists
    if not user_form_session.modified_file_path:
        raise HTTPException(status_code=400, detail="No edited file to export. Run AI Edit first.")

    try:
        # First try to export from DB-stored form version content
        from database_schema import MasterForm, FormVersion

        original_name = os.path.basename(user_form_session.original_file_path).replace(".xml", "")
        export_filename = f"{original_name}_modified.xml"  # Default filename
        file_type = "modified"
        xml_content: str = None

        master = db.query(MasterForm).filter(MasterForm.name == original_name).first()
        if master:
            print(f"🔍 Found master form: {master.name} (ID: {master.id})")
            # Prefer latest by created_at (drafts) created by the current user
            version = (
                db.query(FormVersion)
                .filter(FormVersion.master_form_id == master.id)
                .filter(FormVersion.created_by == current_user.id)
                .order_by(FormVersion.created_at.desc())
                .first()
            )
            if version and version.xml_content:
                print(f"✅ Exporting from DB: version {version.version} (created: {version.created_at})")
                # Create filename with original name + timestamp
                export_filename = f"{original_name}_{version.version}.xml"
                xml_content = version.xml_content
            else:
                print(f"⚠️  No DB version found for user {current_user.id}")
        else:
            print(f"⚠️  No master form found for '{original_name}'")

        if xml_content is None:
            # Fallback to filesystem path resolution
            print(f"🔄 Falling back to filesystem for export")
            print(f"🔍 Modified file path: {user_form_session.modified_file_path}")
            export_file_path = user_form_session.modified_file_path
            if export_file_path == "task_based_edit" or not os.path.isabs(export_file_path):
                import glob
                original_dir = os.path.dirname(os.path.abspath(user_form_session.original_file_path))
                pattern = os.path.join(original_dir, f"modified_{original_name}_*.xml")
                candidates = glob.glob(pattern)
                if candidates:
                    export_file_path = max(candidates, key=os.path.getctime)
                    print(f"📁 Found filesystem file: {export_file_path}")
            if not os.path.exists(export_file_path):
                raise HTTPException(status_code=404, detail="Edited XML file not found")

            filename = os.path.basename(user_form_session.original_file_path)
            export_filename = f"edited_{filename}"

            return FileResponse(
                export_file_path,
                media_type="application/xml",
                filename=export_filename,
                headers={
                    "Content-Disposition": f"attachment; filename={export_filename}",
                    "X-File-Type": file_type,
                    "X-Has-Modifications": "true",
                    "X-Exported-By": current_user.username,
                },
            )

        # Return DB content as file download
        print(f"📄 Serving XML from DB: {len(xml_content)} characters, filename: {export_filename}")
        from fastapi.responses import Response
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename={export_filename}",
                "X-File-Type": file_type,
                "X-Has-Modifications": "true",
                "X-Exported-By": current_user.username,
            },
        )

        # Log export operation
        operation_logger = get_operation_logger()
        operation_logger.log_operation(
            operation_type=OperationType.READ,
            description=f"File exported: {export_filename}",
            target_type="file_export",
            target_name=export_filename,
            user_id=current_user.id,
            success=True,
            after_data={"file_type": file_type, "has_modifications": True}
        )

        return FileResponse(
            export_file_path,
            media_type="application/xml",
            filename=export_filename,
            headers={
                "Content-Disposition": f"attachment; filename={export_filename}",
                "X-File-Type": file_type,
                "X-Has-Modifications": "true",
                "X-Exported-By": current_user.username,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        operation_logger = get_operation_logger()
        operation_logger.log_operation(
            operation_type=OperationType.READ,
            description=f"File export failed",
            target_type="file_export",
            user_id=current_user.id,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Export error: {str(e)}")


@app.post("/api/sessions/reset")
async def reset_active_session(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_database_session)
):
    """Mark any active user form session as completed so a fresh login does not see previous uploads."""
    try:
        from database_schema import UserFormSession, FormWorkStatus
        active = db.query(UserFormSession).filter(
            UserFormSession.user_id == current_user.id,
            UserFormSession.status == FormWorkStatus.ACTIVE.value
        ).all()
        count = 0
        for s in active:
            s.status = FormWorkStatus.COMPLETED.value
            db.add(s)
            count += 1
        db.commit()
        get_operation_logger().log_operation(
            operation_type=OperationType.UPDATE,
            description="Reset active user form sessions",
            target_type="user_form_session",
            user_id=current_user.id,
            success=True,
            after_data={"reset_count": count}
        )
        return {"success": True, "reset_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset sessions: {str(e)}")


@app.get("/api/status")
async def get_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_database_session)
):
    """
    Get current user session status (alias of /api/my-status)

    Shows what file is loaded, if there are modifications, and recent edit history
    """
    from database_schema import UserFormSession, FormWorkStatus
    ufs = db.query(UserFormSession).filter(
        UserFormSession.user_id == current_user.id,
        UserFormSession.status == FormWorkStatus.ACTIVE.value
    ).order_by(UserFormSession.created_at.desc()).first()
    if not ufs:
        return {
            "has_file_uploaded": False,
            "original_file": None,
            "modified_file": None,
            "has_modifications": False,
            "worksheets": [],
            "total_edits": 0,
            "edit_history": [],
            "timestamp": datetime.now().isoformat(),
        }
    analysis = ufs.analysis_json or {}
    worksheets = list(analysis.get("worksheets", {}).keys()) if analysis else []
    history = ufs.edit_history_json or []
    
    # Get a better display name for modified file
    modified_file_display = None
    if ufs.modified_file_path:
        original_name = os.path.basename(ufs.original_file_path).replace(".xml", "")
        # Check if there's a form version in DB for this user
        from database_schema import MasterForm, FormVersion
        master = db.query(MasterForm).filter(MasterForm.name == original_name).first()
        if master:
            version = (
                db.query(FormVersion)
                .filter(FormVersion.master_form_id == master.id)
                .filter(FormVersion.created_by == current_user.id)
                .order_by(FormVersion.created_at.desc())
                .first()
            )
            if version:
                modified_file_display = f"{original_name}_{version.version}.xml"
        
        # Fallback to file path if no DB version
        if not modified_file_display:
            modified_file_display = ufs.modified_file_path
    
    return {
        "has_file_uploaded": True,
        "original_file": ufs.original_file_path,
        "modified_file": modified_file_display,
        "has_modifications": ufs.modified_file_path is not None,
        "worksheets": worksheets,
        "total_edits": len(history),
        "edit_history": history[-5:],
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
