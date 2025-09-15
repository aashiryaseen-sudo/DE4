import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql import func

from database.db import Base  # Import Base from your new database.py file


# =============== ENUMS ===============
# Add all ENUMs required by the hybrid schema
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


# =============== USER MANAGEMENT ===============


class User(Base):
    """User accounts and authentication"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200))
    role = Column(SQLAlchemyEnum(UserRole), nullable=False, default=UserRole.VIEWER)
    is_active = Column(Boolean, default=True, nullable=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships for the hybrid schema
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    created_requests = relationship(
        "CustomizationRequest", back_populates="created_by_user", foreign_keys="[CustomizationRequest.created_by]"
    )
    operations = relationship("FormOperation", back_populates="user")
    created_forms = relationship("Form", back_populates="creator")
    created_versions = relationship("FormVersion", back_populates="creator")


class UserSession(Base):
    """Tracks user login sessions"""

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String(255), unique=True, nullable=False)
    ip_address = Column(String(45))  # Use String for INET to maintain compatibility
    user_agent = Column(Text)
    status = Column(SQLAlchemyEnum(SessionStatus), nullable=False, default=SessionStatus.ACTIVE)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=func.now(), nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    user = relationship("User", back_populates="sessions")


# =============== NEW RELATIONAL FORM MANAGEMENT ===============


class Form(Base):
    """Master Form Definition (corresponds to 'forms' table)"""

    __tablename__ = "forms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    form_id_string = Column(String(255), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    tags = Column(JSON)
    is_active = Column(Boolean, default=True, nullable=False)
    is_template = Column(Boolean, default=True, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    current_version_id = Column(
        Integer, ForeignKey("form_versions.id", use_alter=True, name="fk_current_version"), nullable=True
    )
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    creator = relationship("User", back_populates="created_forms")
    versions = relationship(
        "FormVersion", back_populates="form", cascade="all, delete-orphan", foreign_keys="[FormVersion.form_id]"
    )
    current_version = relationship("FormVersion", foreign_keys=[current_version_id])
    customization_requests = relationship("CustomizationRequest", back_populates="master_form")
    operations = relationship("FormOperation", back_populates="master_form")


class FormVersion(Base):
    """Tracks a specific version of a form (corresponds to 'form_versions' table)"""

    __tablename__ = "form_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    form_id = Column(Integer, ForeignKey("forms.id"), nullable=False)
    version_string = Column(String(50), nullable=False)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=func.now())

    form = relationship("Form", back_populates="versions", foreign_keys=[form_id])
    creator = relationship("User", back_populates="created_versions")
    fields = relationship("FormField", back_populates="form_version", cascade="all, delete-orphan")
    choices = relationship("FormChoice", back_populates="form_version", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("form_id", "version_string", name="uq_form_version"),)


class FormField(Base):
    """UPDATED: A single field/question (a row) from a 'survey' sheet (COMPLETE)"""

    __tablename__ = "form_fields"

    id = Column(Integer, primary_key=True, autoincrement=True)
    form_version_id = Column(Integer, ForeignKey("form_versions.id"), nullable=False)

    # Core Fields
    name = Column(String(255), nullable=False)
    type = Column(String(255), nullable=False)
    label = Column(Text)
    appearance = Column(Text)

    # Logic & Validation Fields
    required = Column(Boolean, default=False)
    relevant = Column(Text)
    hint = Column(Text)
    constraint_formula = Column(Text)
    constraint_message = Column(Text)
    calculation = Column(Text)
    read_only = Column(Boolean, default=False)
    default_value = Column(Text)

    # Grouping
    repeat_count = Column(Text, nullable=True)

    # Deprecated Media Fields
    image = Column(Text, nullable=True)
    audio = Column(Text, nullable=True)
    media_audio = Column("media::audio", Text, nullable=True)
    media_video = Column("media::video", Text, nullable=True)

    # DigiMEP & Asset Management Fields
    timestamp_req = Column(Boolean, default=False)
    include_in_building_profiles = Column(Boolean, default=False)
    equipment_type = Column(String(100), nullable=True)
    equipment_code = Column(String(100), nullable=True)

    # Riptide/Brainbox API Fields
    fetch_data_from_riptide = Column(Boolean, default=False)
    fetch_data_for_field_name = Column(Boolean, default=False)
    riptide_api_prop_name = Column(Text, nullable=True)
    fetch_unit_tag_from_field_name = Column(Text, nullable=True)
    fetch_heat_type_from_field_name = Column(Text, nullable=True)
    fetch_priority_array_from_riptide = Column(Boolean, default=False)
    riptide_timed_override = Column(Boolean, default=False)
    fetch_override_temp_from_field_name = Column(Text, nullable=True)
    cancel_riptide_timed_override = Column(Boolean, default=False)

    # Report & Display Fields
    constraint_check = Column(Boolean, default=True)
    field_order = Column(Integer, nullable=True)
    alias = Column(Text, nullable=True)

    # Relationship
    form_version = relationship("FormVersion", back_populates="fields")

    __table_args__ = (UniqueConstraint("form_version_id", "name", name="uq_form_version_field_name"),)


class FormChoice(Base):
    """A single choice option from 'select_one' or 'select_multiple' sheets"""

    __tablename__ = "form_choices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    form_version_id = Column(Integer, ForeignKey("form_versions.id"), nullable=False)

    list_name = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    label = Column(Text)

    form_version = relationship("FormVersion", back_populates="choices")

    __table_args__ = (UniqueConstraint("form_version_id", "list_name", "name", name="uq_form_version_choice"),)


# =============== CUSTOMIZATION & OPERATIONS (from original schema) ===============


class CustomizationRequest(Base):
    """Tracks user requests for form customization (links to NEW 'forms' table)"""

    __tablename__ = "customization_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(100), unique=True, nullable=False, index=True)
    client_name = Column(String(200), nullable=False)
    form_title = Column(String(200), nullable=False)
    master_form_id = Column(Integer, ForeignKey("forms.id"), nullable=False)  # MODIFIED: Points to new 'forms' table
    raw_request = Column(Text, nullable=False)
    parsed_requirements = Column(JSON, nullable=True)
    selected_equipment_types = Column(JSON, nullable=True)
    field_additions = Column(JSON, nullable=True)
    field_removals = Column(JSON, nullable=True)
    field_modifications = Column(JSON, nullable=True)
    choice_modifications = Column(JSON, nullable=True)
    status = Column(SQLAlchemyEnum(RequestStatus), default=RequestStatus.PENDING, nullable=False)
    priority = Column(Integer, default=3, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    generated_form_version_id = Column(
        Integer, ForeignKey("form_versions.id"), nullable=True
    )  # Points to new 'form_versions' table
    review_notes = Column(JSON, nullable=True)
    iteration_count = Column(Integer, default=0, nullable=False)
    errors_encountered = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    master_form = relationship("Form", back_populates="customization_requests")
    created_by_user = relationship("User", foreign_keys=[created_by], back_populates="created_requests")
    assigned_to_user = relationship("User", foreign_keys=[assigned_to])
    reviewed_by_user = relationship("User", foreign_keys=[reviewed_by])
    generated_form_version = relationship("FormVersion")


class FormOperation(Base):
    """Audit log of every CRUD operation"""

    __tablename__ = "form_operations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_id = Column(String(100), unique=True, nullable=False, index=True)
    operation_type = Column(SQLAlchemyEnum(OperationType), nullable=False)
    operation_description = Column(String(500), nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(String(100), nullable=True)
    target_name = Column(String(200), nullable=True)
    master_form_id = Column(Integer, ForeignKey("forms.id"), nullable=True)  # MODIFIED: Points to new 'forms' table
    form_version_id = Column(
        Integer, ForeignKey("form_versions.id"), nullable=True
    )  # Points to new 'form_versions' table
    customization_request_id = Column(Integer, ForeignKey("customization_requests.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("user_sessions.id"), nullable=True)
    before_data = Column(JSON, nullable=True)
    after_data = Column(JSON, nullable=True)
    operation_parameters = Column(JSON, nullable=True)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="operations")
    session = relationship("UserSession")
    master_form = relationship("Form", back_populates="operations")
    form_version = relationship("FormVersion")
    customization_request = relationship("CustomizationRequest")
