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

class MasterFormUpsertRequest(BaseModel):
    name: str
    current_version: str
    description: Optional[str] = ""
    form_type: Optional[str] = "General"
    client_category: Optional[str] = None
    equipment_types: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = True
    is_template: Optional[bool] = True
    access_level: Optional[str] = "public"
    file_size: Optional[int] = None
    file_checksum: Optional[str] = None

class PurgeConfirmRequest(BaseModel):
    confirm: bool

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
        
        # Get form versions - LIGHTWEIGHT METADATA ONLY
        print("🔍 Starting form versions query...")
        versions_query = session.query(
            FormVersion.id,
            FormVersion.master_form_id,
            FormVersion.version,
            FormVersion.is_current,
            FormVersion.is_published,
            FormVersion.file_size,
            FormVersion.created_by,
            FormVersion.change_summary,
            FormVersion.created_at,
            MasterForm.name
        ).join(MasterForm, FormVersion.master_form_id == MasterForm.id).order_by(FormVersion.created_at.desc()).limit(20)
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
                "master_form_name": version.name,  # Use actual master form name
                "has_xml_content": True  # Assume true for now
            })
        print(f"📋 Found {len(form_versions)} form versions")
        
        # Get user prompts from customization_requests table
        print("🔍 Starting customization requests query...")
        from database_schema import CustomizationRequest
        requests_query = (
            session.query(CustomizationRequest)
            .order_by(CustomizationRequest.created_at.desc())
            .limit(20)
        )
        print("🔍 Customization requests query created, executing...")
        customization_requests = []
        for req in requests_query:
            # Get master form name separately to avoid lazy loading
            master_form_name = None
            if req.master_form_id:
                master = session.query(MasterForm).filter(MasterForm.id == req.master_form_id).first()
                master_form_name = master.name if master else f"Form {req.master_form_id}"
            
            customization_requests.append({
                "id": req.id,
                "prompt": req.raw_request,
                "target_sheet": (req.parsed_requirements or {}).get("target_sheet") if req.parsed_requirements else None,
                "status": req.status.value if hasattr(req.status, 'value') else req.status,
                "timestamp": req.created_at.isoformat(),
                "user_id": req.created_by,
                "client_name": req.client_name,
                "form_title": req.form_title,
                "master_form_id": req.master_form_id,
                "master_form_name": master_form_name,
            })
        print(f"📋 Found {len(customization_requests)} customization requests (user prompts)")
        
        # Get recent operations (audit log)
        print("🔍 Starting operations query...")
        operations_query = session.query(FormOperation).order_by(FormOperation.started_at.desc()).limit(20)
        recent_operations = []
        print(f"🔧 Found {operations_query.count()} operations")
        for op in operations_query:
            recent_operations.append({
                "id": op.id,
                "operation_id": op.operation_id,
                "operation_type": (op.operation_type.value if hasattr(op.operation_type, 'value') else op.operation_type),
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
                "username": op.user.username if op.user else f"User {op.user_id}"
            })
        
        # Get active sessions
        print("🔍 Starting active sessions query...")
        sessions_query = session.query(UserSession).filter(
            UserSession.status == SessionStatus.ACTIVE
        ).order_by(UserSession.last_activity.desc()).limit(20)
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
                "username": sess.user.username if sess.user else f"User {sess.user_id}",
                "user_role": sess.user.role.value if sess.user else "Unknown"
            })
        print(f"🔍 Found {len(active_sessions)} active sessions")
        
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

@app.post("/api/admin/master-forms/import")
async def import_master_form(
    payload: MasterFormUpsertRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_database_session)
):
    """Admin-only: Create or update a master form record ONLY in master_forms.
    If a master form with the same name exists, updates its metadata and current_version.
    """
    try:
        from database_schema import MasterForm
        # Find by name
        master = db.query(MasterForm).filter(MasterForm.name == payload.name).first()
        if not master:
            master = MasterForm(
                form_id=f"form_{uuid.uuid4().hex[:8]}",
                name=payload.name,
                description=payload.description or "",
                current_version=payload.current_version,
                form_type=payload.form_type or "General",
                client_category=payload.client_category,
                equipment_types=payload.equipment_types or [],
                tags=payload.tags or [],
                is_active=payload.is_active if payload.is_active is not None else True,
                is_template=payload.is_template if payload.is_template is not None else True,
                access_level=payload.access_level or "public",
                file_size=payload.file_size,
                file_checksum=payload.file_checksum,
            )
            db.add(master)
            db.commit()
            db.refresh(master)
            get_operation_logger().log_operation(
                operation_type=OperationType.CREATE,
                description=f"Master form created: {payload.name}",
                target_type="master_form",
                target_id=str(master.id),
                target_name=payload.name,
                user_id=admin_user.id,
                success=True
            )
            return {"success": True, "action": "created", "master_form_id": master.id}
        else:
            # Update metadata only
            master.current_version = payload.current_version
            if payload.description is not None:
                master.description = payload.description
            if payload.form_type is not None:
                master.form_type = payload.form_type
            if payload.client_category is not None:
                master.client_category = payload.client_category
            if payload.equipment_types is not None:
                master.equipment_types = payload.equipment_types
            if payload.tags is not None:
                master.tags = payload.tags
            if payload.is_active is not None:
                master.is_active = payload.is_active
            if payload.is_template is not None:
                master.is_template = payload.is_template
            if payload.access_level is not None:
                master.access_level = payload.access_level
            if payload.file_size is not None:
                master.file_size = payload.file_size
            if payload.file_checksum is not None:
                master.file_checksum = payload.file_checksum
            db.commit()
            get_operation_logger().log_operation(
                operation_type=OperationType.UPDATE,
                description=f"Master form updated: {payload.name} -> {payload.current_version}",
                target_type="master_form",
                target_name=payload.name,
                user_id=admin_user.id,
                success=True
            )
            return {"success": True, "action": "updated", "master_form_id": master.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@app.delete("/api/admin/master-forms/{master_form_id}")
async def delete_master_form(
    master_form_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_database_session)
):
    """Admin-only: Delete a master form and its versions."""
    try:
        from database_schema import MasterForm
        master = db.query(MasterForm).filter(MasterForm.id == master_form_id).first()
        if not master:
            raise HTTPException(status_code=404, detail="Master form not found")
        name = master.name
        db.delete(master)
        db.commit()
        get_operation_logger().log_operation(
            operation_type=OperationType.DELETE,
            description=f"Master form deleted: {name}",
            target_type="master_form",
            target_id=str(master_form_id),
            target_name=name,
            user_id=admin_user.id,
            success=True
        )
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@app.get("/api/admin/form-versions/{version_id}/download")
async def download_form_version(
    version_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_database_session)
):
    """Admin-only: Download XML content for a specific form version."""
    try:
        from database_schema import FormVersion
        version = db.query(FormVersion).filter(FormVersion.id == version_id).first()
        if not version:
            raise HTTPException(status_code=404, detail="Form version not found")
        
        # Check if admin user has access to this version (admin can access all, but let's be safe)
        print(f"🔍 Downloading version {version_id} - created_by: {version.created_by}, admin_user: {admin_user.id}")
        
        if not version.xml_content or len(version.xml_content.strip()) == 0:
            print(f"❌ Form version {version_id} has empty XML content (length: {len(version.xml_content) if version.xml_content else 0})")
            print(f"🔍 Version details: created_by={version.created_by}, version={version.version}, created_at={version.created_at}")
            raise HTTPException(status_code=404, detail="No XML content available in this form version")
        
        print(f"✅ Form version {version_id} has XML content (length: {len(version.xml_content)})")
        
        # Generate filename - avoid relationship access
        master_form_name = "Unknown"
        if version.master_form_id:
            master = db.query(MasterForm).filter(MasterForm.id == version.master_form_id).first()
            master_form_name = master.name if master else f"Form_{version.master_form_id}"
        
        filename = f"{master_form_name}_{version.version}.xml"
        
        # Log download
        get_operation_logger().log_operation(
            operation_type=OperationType.READ,
            description=f"Form version downloaded: {filename}",
            target_type="form_version",
            target_id=str(version_id),
            target_name=filename,
            user_id=admin_user.id,
            success=True
        )
        
        # Return XML content as file download
        from fastapi.responses import Response
        return Response(
            content=version.xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Form-Name": master_form_name,
                "X-Version": version.version,
                "X-Created-By": str(version.created_by) if version.created_by else "Unknown"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@app.post("/api/admin/purge-db")
async def purge_database(
    payload: PurgeConfirmRequest,
    admin_user: User = Depends(get_admin_user)
):
    """Admin-only: Drop and recreate all tables. Requires {"confirm": true}."""
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required: set confirm=true")
    try:
        from database_manager import initialize_database
        ok = initialize_database(force_recreate=True)
        get_operation_logger().log_operation(
            operation_type=OperationType.DELETE,
            description="Database purged and recreated",
            target_type="database",
            user_id=admin_user.id,
            success=bool(ok)
        )
        if not ok:
            raise HTTPException(status_code=500, detail="Purge failed")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Purge error: {str(e)}")


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

        # Persist prompt to customization_requests table (initial record)
        customization_request_id = None
        try:
            from database_schema import MasterForm, CustomizationRequest, RequestStatus
            # Derive form context for client_name/form_title
            form_title = os.path.basename(user_form_session.original_file_path).replace(".xml", "")
            client_name = current_user.company or current_user.username or "Unknown"
            master = db.query(MasterForm).filter(MasterForm.name == form_title).first()
            if not master:
                # Ensure a MasterForm exists (required by FK)
                try:
                    from database_manager import get_form_manager
                    with open(working_file, "r", encoding="utf-8") as xf:
                        xml_content_for_master = xf.read()
                    timestamp_version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    get_form_manager().create_master_form(
                        name=form_title,
                        version=timestamp_version,
                        xml_content=xml_content_for_master,
                        description=f"Auto-created from prompt for {form_title}",
                        form_type="General",
                        equipment_types=[],
                        tags=[],
                        created_by=current_user.id
                    )
                    master = db.query(MasterForm).filter(MasterForm.name == form_title).first()
                except Exception as ce:
                    print(f"⚠️ Failed to create MasterForm during request logging: {str(ce)}")
                    db.rollback()
            master_form_id = master.id if master else None

            # Create minimal customization request row capturing the raw prompt
            req = CustomizationRequest(
                request_id=f"req_{uuid.uuid4().hex[:8]}",
                client_name=str(client_name),
                form_title=form_title,
                master_form_id=master_form_id,
                raw_request=prompt,
                parsed_requirements={"target_sheet": target_sheet} if target_sheet else None,
                status=RequestStatus.IN_PROGRESS.value,
                created_by=current_user.id,
            )
            db.add(req)
            db.commit()
            db.refresh(req)
            customization_request_id = req.id
        except Exception as e:
            # Non-fatal: proceed even if request logging fails
            print(f"❌ Failed to create customization request: {str(e)}")
            db.rollback()

        # Process the prompt using the ReAct agent
        print(f"🔍 Processing AI edit prompt: {enhanced_prompt}")
        result = await agent.process_prompt(enhanced_prompt)
        print(f"🔍 AI edit result: {result}")
        
        # Check if the agent created a modified file
        modified_file_created = False
        latest_modified = None
        
        # Look for modified files created by the agent
        import glob
        original_name = os.path.basename(user_form_session.original_file_path).replace(".xml", "")
        pattern = str(Path(user_form_session.original_file_path).parent / f"modified_{original_name}_*.xml")
        print(f"🔍 Looking for modified files with pattern: {pattern}")
        modified_files = glob.glob(pattern)
        print(f"🔍 Found {len(modified_files)} modified files: {modified_files}")
        
        if modified_files:
            latest_modified = max(modified_files, key=os.path.getctime)
            modified_file_created = True
            print(f"✅ Using latest modified file: {latest_modified}")
        else:
            print(f"🔍 No modified files found, will check for task-based edits")
        
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


        # Check for success indicators
        success_indicators = [
            "successfully added",
            "added choice option",
            "modified_file_path",
            "_modified.xml",
            "backup_created",
        ]

        response_lower = result["agent_response"].lower()
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
        
        # Check for failure indicators in the response
        has_failure_indicators = any([
            'could not be completed' in agent_response.lower(),
            'was not found' in agent_response.lower(),
            'not found' in agent_response.lower(),
            'error' in agent_response.lower(),
            'failed' in agent_response.lower(),
            'unable to' in agent_response.lower()
        ])
        
        # Determine if changes were actually applied
        changes_applied = modified_file_created or (has_successful_tasks and not has_failure_indicators)
        actual_success = changes_applied and (tool_calls_made > 0 or has_successful_tasks) and not has_failure_indicators
        
        # Update history regardless of success/failure
        history = user_form_session.edit_history_json or []
        history.append({
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "target_sheet": target_sheet,
            "success": actual_success,
            "changes_applied": changes_applied,
        })
        user_form_session.edit_history_json = history
        
        # Only proceed with success path if we actually have changes
        if actual_success:
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

                # Read XML content from the appropriate source
                xml_content = ""
                
                if latest_modified and os.path.exists(latest_modified):
                    # Use the modified file created by the agent
                    try:
                        with open(latest_modified, "r", encoding="utf-8") as xf:
                            xml_content = xf.read()
                        print(f"✅ Read modified XML content from file: {len(xml_content)} characters from {latest_modified}")
                    except Exception as e:
                        print(f"❌ Failed to read modified file {latest_modified}: {str(e)}")
                        raise HTTPException(status_code=500, detail="Failed to read modified XML content")
                else:
                    # Check if this is a task-based edit (no file created but changes made)
                    has_successful_tasks = any([
                        '"status": "completed"' in result.get("agent_response", ""),
                        '"completed_tasks"' in result.get("agent_response", ""),
                        'Successfully completed' in result.get("agent_response", ""),
                        '✅' in result.get("agent_response", ""),
                        '"execution_completed": true' in result.get("agent_response", "")
                    ])
                    
                    if has_successful_tasks:
                        # For task-based edits, we need to get the XML from the original file
                        # since no physical file was created but changes were made in memory
                        print(f"🔍 Task-based edit detected, reading from original file: {working_file}")
                        try:
                            with open(working_file, "r", encoding="utf-8") as xf:
                                xml_content = xf.read()
                            print(f"📄 Read XML content from original file: {len(xml_content)} characters")
                        except Exception as e:
                            print(f"❌ Failed to read original file {working_file}: {str(e)}")
                            raise HTTPException(status_code=500, detail="Failed to read XML content for database storage")
                    else:
                        # No modifications were made, use original file
                        print(f"🔍 No modifications detected, using original file: {working_file}")
                        try:
                            with open(working_file, "r", encoding="utf-8") as xf:
                                xml_content = xf.read()
                            print(f"📄 Read XML content from original file: {len(xml_content)} characters")
                        except Exception as e:
                            print(f"❌ Failed to read original file {working_file}: {str(e)}")
                            raise HTTPException(status_code=500, detail="Failed to read XML content for database storage")
                
                # Ensure we have XML content
                if not xml_content or len(xml_content.strip()) == 0:
                    print(f"❌ XML content is empty or whitespace only (length: {len(xml_content)})")
                    print(f"🔍 DEBUG: This means the AI edit did not create any modifications")
                    raise HTTPException(status_code=500, detail="No XML content available to save to database")
                
                print(f"✅ XML content ready for database storage: {len(xml_content)} characters")
                print(f"🔍 DEBUG: XML starts with: {xml_content[:100]}...")

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
                        file_path=latest_modified if latest_modified else "task_based_edit",
                        file_size=os.path.getsize(latest_modified) if latest_modified and os.path.exists(latest_modified) else None,
                        file_checksum=None,
                        created_by=current_user.id,
                        change_summary=f"AI edit: {prompt[:50]}..." if len(prompt) > 50 else f"AI edit: {prompt}",
                        is_current=False,
                        is_published=False,
                    )
                    db.add(new_version)
                    db.commit()
                    print(f"✅ Saved version to DB: {new_version.version} with {len(xml_content)} characters")
                    print(f"🔍 DEBUG: XML content preview: {xml_content[:200]}...")
                    
                    # Verify what was actually saved
                    saved_version = db.query(FormVersion).filter(FormVersion.id == new_version.id).first()
                    if saved_version:
                        saved_xml_len = len(saved_version.xml_content) if saved_version.xml_content else 0
                        print(f"🔍 DEBUG: Verified saved XML length: {saved_xml_len}")
                        if saved_xml_len == 0:
                            print(f"❌ WARNING: XML content was not saved properly!")
                    else:
                        print(f"❌ ERROR: Could not retrieve saved version from DB")

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

            # Update customization request as completed
            try:
                if customization_request_id:
                    from database_schema import CustomizationRequest, RequestStatus
                    req = db.query(CustomizationRequest).get(customization_request_id)
                    if req:
                        req.status = RequestStatus.APPROVED.value if actual_success else RequestStatus.REVISION_REQUESTED.value
                        req.processing_completed_at = datetime.utcnow()
                        db.add(req)
                        db.commit()
            except Exception as e:
                print(f"⚠️ Failed to update customization request status: {str(e)}")
                db.rollback()

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
                    "changes_applied": modified_file_created,
                    "customization_request_id": customization_request_id
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
            # AI edit failed - no changes were applied
            db.commit()  # Commit the history update
            
            # Update customization request as failed
            try:
                if customization_request_id:
                    from database_schema import CustomizationRequest, RequestStatus
                    req = db.query(CustomizationRequest).get(customization_request_id)
                    if req:
                        req.status = RequestStatus.REVISION_REQUESTED.value
                        req.processing_completed_at = datetime.utcnow()
                        db.add(req)
                        db.commit()
            except Exception as e2:
                print(f"⚠️ Failed to update customization request (failure path): {str(e2)}")
                db.rollback()

            operation_logger = get_operation_logger()
            operation_logger.log_operation(
                operation_type=OperationType.UPDATE,
                description=f"AI edit failed: {prompt[:100]}",
                target_type="xml_file",
                target_name=current_uploaded_file,
                user_id=current_user.id,
                success=False,
                error_message=result.get("error", "No changes were applied"),
                after_data={"customization_request_id": customization_request_id}
            )
            return {"success": False, "error": result.get("error", "No changes were applied"), "prompt": prompt, "target_sheet": target_sheet}

    except Exception as e:
        # Log exception
        # Update customization request as failed (exception path)
        try:
            if 'customization_request_id' in locals() and customization_request_id:
                from database_schema import CustomizationRequest, RequestStatus
                req = db.query(CustomizationRequest).get(customization_request_id)
                if req:
                    req.status = RequestStatus.REVISION_REQUESTED.value
                    req.processing_completed_at = datetime.utcnow()
                    db.add(req)
                    db.commit()
        except Exception as e2:
            print(f"⚠️ Failed to update customization request (exception path): {str(e2)}")
            db.rollback()

        operation_logger = get_operation_logger()
        operation_logger.log_operation(
            operation_type=OperationType.UPDATE,
            description=f"AI edit exception: {prompt[:100]}",
            target_type="xml_file",
            target_name=current_uploaded_file,
            user_id=current_user.id,
            success=False,
            error_message=str(e),
            after_data={"customization_request_id": customization_request_id}
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
        # Export from DB-stored form version content ONLY
        from database_schema import MasterForm, FormVersion

        original_name = os.path.basename(user_form_session.original_file_path).replace(".xml", "")
        export_filename = f"{original_name}_modified.xml"  # Default filename
        file_type = "modified"
        xml_content: str = None

        # Find master form
        master = db.query(MasterForm).filter(MasterForm.name == original_name).first()
        if not master:
            raise HTTPException(status_code=404, detail=f"Master form '{original_name}' not found in database")
        
        print(f"🔍 Found master form: {master.name} (ID: {master.id})")
        
        # Get latest version created by current user
        version = (
            db.query(FormVersion)
            .filter(FormVersion.master_form_id == master.id)
            .filter(FormVersion.created_by == current_user.id)
            .order_by(FormVersion.created_at.desc())
            .first()
        )
        
        if not version:
            raise HTTPException(status_code=404, detail="No edited version found. Please run AI Edit first.")
        
        if not version.xml_content:
            raise HTTPException(status_code=404, detail="No XML content available in the edited version")
        
        print(f"✅ Exporting from DB: version {version.version} (created: {version.created_at})")
        export_filename = f"{original_name}_{version.version}.xml"
        xml_content = version.xml_content

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
                "X-Version": version.version,
                "X-Created-At": version.created_at.isoformat()
            },
        )

        # Log export operation
        operation_logger = get_operation_logger()
        operation_logger.log_operation(
            operation_type=OperationType.READ,
            description=f"File exported from DB: {export_filename}",
            target_type="file_export",
            target_name=export_filename,
            user_id=current_user.id,
            success=True,
            after_data={"file_type": file_type, "has_modifications": True, "source": "database"}
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
    
    # Count only successful edits (same logic as AI edit endpoint)
    successful_edits = [edit for edit in history if edit.get("success", False)]
    
    return {
        "has_file_uploaded": True,
        "original_file": ufs.original_file_path,
        "modified_file": modified_file_display,
        "has_modifications": len(successful_edits) > 0,  # Only true if there are successful edits
        "worksheets": worksheets,
        "total_edits": len(successful_edits),  # Only count successful edits
        "edit_history": history[-5:],
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
