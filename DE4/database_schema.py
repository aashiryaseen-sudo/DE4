"""
DE4 Database Schema
Comprehensive database design for XML Forms Platform
"""

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, 
    ForeignKey, JSON, Enum, Float, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine
import os
from datetime import datetime
import enum
import uuid
from typing import Optional

Base = declarative_base()

# =============== ENUMS ===============

class UserRole(enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    EDITOR = "editor"
    VIEWER = "viewer"

class RequestStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    READY_FOR_REVIEW = "ready_for_review"
    UNDER_REVIEW = "under_review"
    REVISION_REQUESTED = "revision_requested"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    CANCELLED = "cancelled"

class OperationType(enum.Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    CLONE = "clone"
    DEPLOY = "deploy"

class SessionStatus(enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"

class FormWorkStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"

# =============== USER MANAGEMENT ===============

class User(Base):
    """User accounts and authentication"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=True)
    role = Column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=UserRole.VIEWER.value,
    )
    
    # Profile info
    company = Column(String(200), nullable=True)
    department = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    last_login = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    # Explicitly tie this relationship to CustomizationRequest.created_by to avoid multiple FK path ambiguity
    requests = relationship(
        "CustomizationRequest",
        back_populates="created_by_user",
        foreign_keys="CustomizationRequest.created_by",
        primaryjoin="User.id==CustomizationRequest.created_by",
    )
    operations = relationship("FormOperation", back_populates="user")
    
    def __repr__(self):
        return f"<User(username='{self.username}', role='{self.role}')>"

class UserSession(Base):
    """Handle concurrent login sessions"""
    __tablename__ = 'user_sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    session_token = Column(String(255), unique=True, nullable=False, index=True)
    
    # Session details
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    device_info = Column(JSON, nullable=True)
    
    # Session management
    status = Column(
        Enum(
            SessionStatus,
            name="session_status",
            native_enum=True,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        default=SessionStatus.ACTIVE.value,
        nullable=False,
    )
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    terminated_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    
    # Indexes
    __table_args__ = (
        Index('idx_session_token', 'session_token'),
        Index('idx_user_active_sessions', 'user_id', 'status'),
        Index('idx_session_expiry', 'expires_at'),
    )
    
    def __repr__(self):
        return f"<UserSession(user_id={self.user_id}, status='{self.status}')>"

# =============== FORM MANAGEMENT ===============

class MasterForm(Base):
    """Master form metadata and versions"""
    __tablename__ = 'master_forms'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    form_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Version management
    current_version = Column(String(20), nullable=False)
    version_count = Column(Integer, default=1, nullable=False)
    
    # Form metadata
    form_type = Column(String(50), nullable=True)  # e.g., 'HVAC', 'PM', 'Inspection'
    client_category = Column(String(100), nullable=True)  # e.g., 'Commercial', 'Industrial'
    equipment_types = Column(JSON, nullable=True)  # List of equipment types supported
    tags = Column(JSON, nullable=True)  # Search tags
    
    # Status and visibility
    is_active = Column(Boolean, default=True, nullable=False)
    is_template = Column(Boolean, default=True, nullable=False)
    access_level = Column(String(20), default='public', nullable=False)  # public, restricted, private
    
    # Statistics
    usage_count = Column(Integer, default=0, nullable=False)  # How many times cloned
    field_count = Column(Integer, default=0, nullable=False)
    section_count = Column(Integer, default=0, nullable=False)
    
    # File info
    file_size = Column(Integer, nullable=True)  # in bytes
    file_checksum = Column(String(64), nullable=True)  # SHA-256
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    versions = relationship("FormVersion", back_populates="master_form", cascade="all, delete-orphan")
    customization_requests = relationship("CustomizationRequest", back_populates="master_form")
    
    # Indexes
    __table_args__ = (
        Index('idx_master_form_name', 'name'),
        Index('idx_master_form_type', 'form_type'),
        Index('idx_master_form_active', 'is_active'),
        Index('idx_master_form_template', 'is_template'),
    )
    
    def __repr__(self):
        return f"<MasterForm(name='{self.name}', version='{self.current_version}')>"

class FormVersion(Base):
    """Complete version history with XML content"""
    __tablename__ = 'form_versions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    master_form_id = Column(Integer, ForeignKey('master_forms.id'), nullable=False)
    version = Column(String(255), nullable=False)
    
    # Version details
    version_notes = Column(Text, nullable=True)
    is_current = Column(Boolean, default=False, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False)
    
    # XML Content - stored as compressed text for large forms
    xml_content = Column(Text, nullable=False)  # Complete XML content
    xml_compressed = Column(Boolean, default=False, nullable=False)
    
    # Form structure metadata (for quick queries without parsing XML)
    form_structure = Column(JSON, nullable=True)  # Parsed structure summary
    field_names = Column(JSON, nullable=True)  # List of all field names
    choice_lists = Column(JSON, nullable=True)  # List of all choice lists
    
    # File information
    file_path = Column(String(500), nullable=True)  # Original file path if stored separately
    file_size = Column(Integer, nullable=True)
    file_checksum = Column(String(64), nullable=True)
    
    # Version metadata
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    change_summary = Column(Text, nullable=True)  # Summary of changes from previous version
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    master_form = relationship("MasterForm", back_populates="versions")
    created_by_user = relationship("User")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('master_form_id', 'version', name='uq_form_version'),
        Index('idx_form_version_current', 'master_form_id', 'is_current'),
        Index('idx_form_version_published', 'is_published'),
    )
    
    def __repr__(self):
        return f"<FormVersion(master_form_id={self.master_form_id}, version='{self.version}')>"

# =============== CUSTOMIZATION SYSTEM ===============

class CustomizationRequest(Base):
    """Track all user requests for form customization"""
    __tablename__ = 'customization_requests'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Request details
    client_name = Column(String(200), nullable=False)
    form_title = Column(String(200), nullable=False)
    master_form_id = Column(Integer, ForeignKey('master_forms.id'), nullable=False)
    
    # Request content
    raw_request = Column(Text, nullable=False)  # Original natural language request
    parsed_requirements = Column(JSON, nullable=True)  # AI-parsed requirements
    
    # Equipment selection
    selected_equipment_types = Column(JSON, nullable=True)  # List of selected equipment
    excluded_equipment_types = Column(JSON, nullable=True)  # List of excluded equipment
    
    # Customizations
    field_additions = Column(JSON, nullable=True)  # Fields to add
    field_removals = Column(JSON, nullable=True)  # Fields to remove
    field_modifications = Column(JSON, nullable=True)  # Fields to modify
    choice_modifications = Column(JSON, nullable=True)  # Choice list changes
    
    # Workflow management
    status = Column(
        Enum(
            RequestStatus,
            name="request_status",
            native_enum=True,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        default=RequestStatus.PENDING.value,
        nullable=False,
    )
    priority = Column(Integer, default=3, nullable=False)  # 1=High, 2=Medium, 3=Low
    
    # Assignment and review
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    assigned_to = Column(Integer, ForeignKey('users.id'), nullable=True)
    reviewed_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Processing details
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    
    # Output
    generated_form_path = Column(String(500), nullable=True)
    generated_form_version_id = Column(Integer, ForeignKey('form_versions.id'), nullable=True)
    
    # Quality and feedback
    quality_score = Column(Float, nullable=True)  # 0-100 quality score
    review_notes = Column(JSON, nullable=True)  # List of review comments
    feedback_summary = Column(Text, nullable=True)
    
    # Metrics
    iteration_count = Column(Integer, default=0, nullable=False)
    customizations_applied = Column(Integer, default=0, nullable=False)
    errors_encountered = Column(JSON, nullable=True)
    warnings_generated = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    master_form = relationship("MasterForm", back_populates="customization_requests")
    created_by_user = relationship("User", foreign_keys=[created_by], back_populates="requests")
    assigned_to_user = relationship("User", foreign_keys=[assigned_to])
    reviewed_by_user = relationship("User", foreign_keys=[reviewed_by])
    generated_form_version = relationship("FormVersion")
    operations = relationship("FormOperation", back_populates="customization_request")
    
    # Indexes
    __table_args__ = (
        Index('idx_request_status', 'status'),
        Index('idx_request_created_by', 'created_by'),
        Index('idx_request_assigned_to', 'assigned_to'),
        Index('idx_request_priority', 'priority'),
        Index('idx_request_created_at', 'created_at'),
        Index('idx_request_master_form', 'master_form_id'),
    )
    
    def __repr__(self):
        return f"<CustomizationRequest(request_id='{self.request_id}', status='{self.status}')>"

# =============== AUDIT AND OPERATIONS ===============

class FormOperation(Base):
    """Audit log of every CRUD operation"""
    __tablename__ = 'form_operations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Operation details
    operation_type = Column(
        Enum(
            OperationType,
            name="operation_type",
            native_enum=True,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    )
    operation_description = Column(String(500), nullable=False)
    
    # Target information
    target_type = Column(String(50), nullable=False)  # 'master_form', 'form_version', 'field', 'choice'
    target_id = Column(String(100), nullable=True)  # ID of the target object
    target_name = Column(String(200), nullable=True)  # Name/title of target
    
    # Form context
    master_form_id = Column(Integer, ForeignKey('master_forms.id'), nullable=True)
    form_version_id = Column(Integer, ForeignKey('form_versions.id'), nullable=True)
    customization_request_id = Column(Integer, ForeignKey('customization_requests.id'), nullable=True)
    
    # Operation context
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    session_id = Column(Integer, ForeignKey('user_sessions.id'), nullable=True)
    
    # Operation data
    before_data = Column(JSON, nullable=True)  # State before operation
    after_data = Column(JSON, nullable=True)  # State after operation
    operation_parameters = Column(JSON, nullable=True)  # Parameters passed to operation
    
    # Result information
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    warnings = Column(JSON, nullable=True)
    
    # Performance metrics
    execution_time_ms = Column(Integer, nullable=True)
    memory_usage_mb = Column(Float, nullable=True)
    
    # Client information
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="operations")
    session = relationship("UserSession")
    master_form = relationship("MasterForm")
    form_version = relationship("FormVersion")
    customization_request = relationship("CustomizationRequest", back_populates="operations")
    
    # Indexes
    __table_args__ = (
        Index('idx_operation_type', 'operation_type'),
        Index('idx_operation_user', 'user_id'),
        Index('idx_operation_target', 'target_type', 'target_id'),
        Index('idx_operation_timestamp', 'started_at'),
        Index('idx_operation_success', 'success'),
        Index('idx_operation_master_form', 'master_form_id'),
        Index('idx_operation_request', 'customization_request_id'),
    )
    
    def __repr__(self):
        return f"<FormOperation(operation_type='{self.operation_type}', target='{self.target_name}')>"

# =============== DATABASE CONFIGURATION ===============

# =============== USER FORM SESSIONS (PER-USER WORKFLOW) ===============

class UserFormSession(Base):
    """Per-user working session for uploaded/edited forms"""
    __tablename__ = 'user_form_sessions'

    id = Column(String(36), primary_key=True, nullable=False)  # UUID string
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    status = Column(
        Enum(
            FormWorkStatus,
            name="form_work_status",
            native_enum=True,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        default=FormWorkStatus.ACTIVE.value,
        nullable=False,
    )
    original_file_path = Column(String(500), nullable=True)
    modified_file_path = Column(String(500), nullable=True)
    analysis_json = Column(JSON, nullable=True)
    edit_history_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User")

    def __repr__(self):
        return f"<UserFormSession(id='{self.id}', user_id={self.user_id}, status='{self.status}')>"

class DatabaseConfig:
    """Database configuration and connection management"""
    
    def __init__(self, database_url: str = None):
        if database_url is None:
            # Prefer env DATABASE_URL; if missing, keep explicit None to surface errors downstream
            database_url = os.getenv("DATABASE_URL")
        
        self.database_url = database_url or ""

        # Determine engine options from env
        echo_sql = os.getenv("SQLALCHEMY_ECHO", "false").lower() in ("1", "true", "yes")
        pool_recycle = int(os.getenv("DB_POOL_RECYCLE_SEC", "3600"))

        # SSL options for Supabase/Postgres
        connect_args = {}
        if self.database_url.startswith("postgres"):
            # Supabase often requires sslmode=require
            # SQLAlchemy psycopg2 will pass these via connect_args
            sslmode = os.getenv("DB_SSLMODE", "require")
            if sslmode:
                connect_args["sslmode"] = sslmode
            sslrootcert = os.getenv("DB_SSLROOTCERT")
            if sslrootcert:
                connect_args["sslrootcert"] = sslrootcert

        if not self.database_url:
            # Create a placeholder engine that will error clearly when used
            self.engine = create_engine(
                "sqlite:///missing_database_url.db",
                echo=echo_sql,
                pool_pre_ping=True,
                pool_recycle=pool_recycle,
            )
        else:
            self.engine = create_engine(
                self.database_url,
                echo=echo_sql,
                pool_pre_ping=True,
                pool_recycle=pool_recycle,
                connect_args=connect_args,
            )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            bind=self.engine
        )
    
    def create_all_tables(self):
        """Create all database tables"""
        Base.metadata.create_all(bind=self.engine)
    
    def drop_all_tables(self):
        """Drop all database tables (use with caution!)"""
        Base.metadata.drop_all(bind=self.engine)
    
    def get_session(self):
        """Get database session"""
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()

# =============== HELPER FUNCTIONS ===============

def generate_uuid() -> str:
    """Generate a UUID string"""
    return str(uuid.uuid4())

def get_database_stats(session) -> dict:
    """Get database statistics"""
    stats = {}
    
    # Count records in each table
    stats['users'] = session.query(User).count()
    stats['active_sessions'] = session.query(UserSession).filter(UserSession.status == SessionStatus.ACTIVE).count()
    stats['master_forms'] = session.query(MasterForm).count()
    stats['active_master_forms'] = session.query(MasterForm).filter(MasterForm.is_active == True).count()
    stats['form_versions'] = session.query(FormVersion).count()
    stats['customization_requests'] = session.query(CustomizationRequest).count()
    stats['pending_requests'] = session.query(CustomizationRequest).filter(CustomizationRequest.status == RequestStatus.PENDING).count()
    stats['form_operations'] = session.query(FormOperation).count()
    
    return stats

# Export main components
__all__ = [
    'Base',
    'User', 'UserSession',
    'MasterForm', 'FormVersion',
    'CustomizationRequest', 'FormOperation',
    'DatabaseConfig',
    'UserRole', 'RequestStatus', 'OperationType', 'SessionStatus',
    'generate_uuid', 'get_database_stats'
]
