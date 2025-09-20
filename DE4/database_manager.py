"""
DE4 Database Manager
Database initialization, connection management, and utilities
"""

import os
from dotenv import load_dotenv
import logging
from typing import Generator, Optional, Dict, Any, List
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
import hashlib
import json
from urllib.parse import urlparse, urlunparse

from database_schema import (
    DatabaseConfig, Base,
    User, UserSession, MasterForm, FormVersion,
    CustomizationRequest, FormOperation,
    UserRole, RequestStatus, OperationType, SessionStatus,
    generate_uuid, get_database_stats
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env if present (so DATABASE_URL/OPENAI_API_KEY are available)
load_dotenv()

class DatabaseManager:
    """Central database manager for DE4 platform"""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager
        
        Args:
            database_url: Database connection URL. If None, uses environment variable or SQLite default.
        """
        if database_url is None:
            database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.warning("DATABASE_URL is not set. Database operations will fail until configured.")
        
        self.config = DatabaseConfig(database_url)
        self._initialized = False
    
    def initialize_database(self, force_recreate: bool = False) -> bool:
        """Initialize database with all tables and basic data
        
        Args:
            force_recreate: If True, drops and recreates all tables
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if force_recreate:
                logger.warning("Force recreating database - all data will be lost!")
                self.config.drop_all_tables()
            
            # Create all tables (no-op if they already exist)
            self.config.create_all_tables()
            
            # Create default admin user if none exists
            with self.get_session() as session:
                # Avoid duplicate username conflicts if a non-admin 'admin' exists
                # Compare against the enum value for Postgres enum type compatibility
                existing_admin_or_username = session.query(User).filter(
                    (User.role == UserRole.ADMIN.value) | (User.username == "admin")
                ).first()
                if not existing_admin_or_username:
                    self._create_default_admin(session)
                    session.commit()
            
            self._initialized = True
            logger.info("Database initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Database initialization failed: {str(e)}")
            return False
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get database session with automatic cleanup"""
        session = self.config.SessionLocal()
        try:
            yield session
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {str(e)}")
            raise
        finally:
            session.close()
    
    def get_session_dependency(self):
        """FastAPI dependency for getting database session"""
        return self.config.get_session()
    
    def _create_default_admin(self, session: Session):
        """Create default admin user"""
        # Read admin seed from environment, with safe defaults
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
        admin_email = os.getenv("ADMIN_EMAIL", "admin@de4platform.com")
        admin_full_name = os.getenv("ADMIN_FULL_NAME", "System Administrator")

        admin_user = User(
            username=admin_username,
            email=admin_email,
            password_hash=self._hash_password(admin_password),
            full_name=admin_full_name,
            role=UserRole.ADMIN.value,
            company="DE4 Platform",
            is_active=True,
            is_verified=True
        )
        session.add(admin_user)
        logger.info(f"Created default admin user (username: {admin_username})")
    
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256 (use bcrypt in production)"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def health_check(self) -> Dict[str, Any]:
        """Check database health and return status"""
        try:
            with self.get_session() as session:
                # Test basic query
                user_count = session.query(User).count()
                stats = get_database_stats(session)
                
                return {
                    "status": "healthy",
                    "database_url": self.config.database_url.split('@')[-1] if self.config.database_url and '@' in self.config.database_url else self.config.database_url,
                    "initialized": self._initialized,
                    "stats": stats,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def cleanup_expired_sessions(self) -> int:
        """Clean up expired user sessions"""
        try:
            with self.get_session() as session:
                expired_sessions = session.query(UserSession).filter(
                    UserSession.expires_at < datetime.utcnow(),
                    UserSession.status == SessionStatus.ACTIVE
                ).all()
                
                count = len(expired_sessions)
                for session_obj in expired_sessions:
                    session_obj.status = SessionStatus.EXPIRED
                    session_obj.terminated_at = datetime.utcnow()
                
                session.commit()
                logger.info(f"Cleaned up {count} expired sessions")
                return count
                
        except Exception as e:
            logger.error(f"Session cleanup failed: {str(e)}")
            return 0

    def test_connection(self) -> Dict[str, Any]:
        """Attempt a direct connection and return verbose diagnostics"""
        info: Dict[str, Any] = {
            "database_url": self.config.database_url,
        }
        try:
            # Try to connect and run simple statements using SQLAlchemy 2.0 API
            with self.config.engine.connect() as conn:
                server_version = None
                try:
                    server_version = conn.exec_driver_sql("SHOW server_version").scalar()
                except Exception:
                    # Not all drivers support SHOW server_version; ignore
                    pass

                one = conn.exec_driver_sql("SELECT 1").scalar()
                info.update({
                    "connected": True,
                    "server_version": server_version,
                    "select1": one,
                })
                return info
        except Exception as e:
            info.update({
                "connected": False,
                "error": str(e),
            })
            logger.error(f"DB connection test failed: {e}")
            return info

    # ---- Debug helpers ----
    def _masked_url(self, url: Optional[str]) -> str:
        if not url:
            return "<NOT SET>"
        try:
            parsed = urlparse(url)
            netloc = parsed.hostname or "";
            if parsed.port:
                netloc += f":{parsed.port}"
            # Obscure username and password but keep presence
            userinfo = []
            if parsed.username:
                userinfo.append("***")
            if parsed.password:
                userinfo.append("***")
            prefix = "" if not userinfo else (":".join(userinfo) + "@")
            netloc = prefix + netloc
            masked = urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
            return masked
        except Exception:
            return "<MASK FAILED>"

    def debug_summary(self) -> Dict[str, Any]:
        """Return environment-driven DB config summary with masked URL."""
        return {
            "database_url_masked": self._masked_url(self.config.database_url),
            "echo_sql": os.getenv("SQLALCHEMY_ECHO", "false"),
            "sslmode": os.getenv("DB_SSLMODE", "require"),
            "pool_recycle_sec": os.getenv("DB_POOL_RECYCLE_SEC", "3600"),
        }
    
    def backup_database(self, backup_path: str) -> bool:
        """Create database backup"""
        try:
            if self.config.database_url.startswith('sqlite'):
                # SQLite backup
                import shutil
                db_path = self.config.database_url.replace('sqlite:///', '')
                shutil.copy2(db_path, backup_path)
                logger.info(f"SQLite database backed up to {backup_path}")
                return True
                
            elif self.config.database_url.startswith('postgresql'):
                # PostgreSQL backup using pg_dump
                import subprocess
                from urllib.parse import urlparse
                
                parsed = urlparse(self.config.database_url)
                cmd = [
                    'pg_dump',
                    '-h', parsed.hostname or 'localhost',
                    '-p', str(parsed.port or 5432),
                    '-U', parsed.username,
                    '-d', parsed.path.lstrip('/'),
                    '-f', backup_path
                ]
                
                env = os.environ.copy()
                if parsed.password:
                    env['PGPASSWORD'] = parsed.password
                
                result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"PostgreSQL database backed up to {backup_path}")
                    return True
                else:
                    logger.error(f"pg_dump failed: {result.stderr}")
                    return False
            else:
                logger.warning(f"Backup not supported for database type: {self.config.database_url.split('://')[0]}")
                return False
                
        except Exception as e:
            logger.error(f"Database backup failed: {str(e)}")
            return False

class UserManager:
    """User management utilities"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def create_user(self, username: str, email: str, password: str, 
                   full_name: str = "", role: UserRole = UserRole.VIEWER,
                   **kwargs) -> Optional[User]:
        """Create new user"""
        try:
            with self.db_manager.get_session() as session:
                # Check if user exists
                existing = session.query(User).filter(
                    (User.username == username) | (User.email == email)
                ).first()
                
                if existing:
                    logger.warning(f"User already exists: {username} or {email}")
                    return None
                
                # Create new user
                # Normalize role for DB (string value for Postgres enum)
                normalized_role = role.value if hasattr(role, 'value') else role

                user = User(
                    username=username,
                    email=email,
                    password_hash=self.db_manager._hash_password(password),
                    full_name=full_name,
                    role=normalized_role,
                    **kwargs
                )
                
                session.add(user)
                session.commit()
                session.refresh(user)
                
                logger.info(f"Created user: {username}")
                return user
                
        except Exception as e:
            logger.error(f"User creation failed: {str(e)}")
            return None
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user credentials"""
        try:
            with self.db_manager.get_session() as session:
                user = session.query(User).filter(
                    User.username == username,
                    User.is_active == True
                ).first()
                
                if user and user.password_hash == self.db_manager._hash_password(password):
                    # Update last login
                    user.last_login = datetime.utcnow()
                    session.commit()
                    return user
                
                return None
                
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            return None
    
    def create_session(self, user_id: int, ip_address: str = None, 
                      user_agent: str = None, expires_hours: int = 24) -> Optional[UserSession]:
        """Create new user session"""
        try:
            with self.db_manager.get_session() as session:
                # Generate session token
                session_token = generate_uuid()
                expires_at = datetime.utcnow() + timedelta(hours=expires_hours)
                
                user_session = UserSession(
                    user_id=user_id,
                    session_token=session_token,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    expires_at=expires_at
                )
                
                session.add(user_session)
                session.commit()
                session.refresh(user_session)
                
                logger.info(f"Created session for user {user_id}")
                return user_session
                
        except Exception as e:
            logger.error(f"Session creation failed: {str(e)}")
            return None
    
    def validate_session(self, session_token: str) -> Optional[User]:
        """Validate session token and return user"""
        try:
            with self.db_manager.get_session() as session:
                user_session = session.query(UserSession).filter(
                    UserSession.session_token == session_token,
                    UserSession.status == SessionStatus.ACTIVE,
                    UserSession.expires_at > datetime.utcnow()
                ).first()
                
                if user_session:
                    # Update last activity
                    user_session.last_activity = datetime.utcnow()
                    session.commit()
                    return user_session.user
                
                return None
                
        except Exception as e:
            logger.error(f"Session validation failed: {str(e)}")
            return None

class FormManager:
    """Form management utilities"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def create_master_form(self, name: str, version: str, xml_content: str,
                          description: str = "", form_type: str = "",
                          equipment_types: List[str] = None, tags: List[str] = None,
                          created_by: int = None) -> Optional[MasterForm]:
        """Create new master form with initial version"""
        try:
            with self.db_manager.get_session() as session:
                # Check if form exists
                existing = session.query(MasterForm).filter(
                    MasterForm.name == name,
                    MasterForm.current_version == version
                ).first()
                
                if existing:
                    logger.warning(f"Master form already exists: {name} v{version}")
                    return None
                
                # Generate form ID
                form_id = f"form_{generate_uuid()[:8]}"
                
                # Calculate file info
                file_size = len(xml_content.encode('utf-8'))
                file_checksum = hashlib.sha256(xml_content.encode('utf-8')).hexdigest()
                
                # Create master form
                master_form = MasterForm(
                    form_id=form_id,
                    name=name,
                    description=description,
                    current_version=version,
                    form_type=form_type,
                    equipment_types=equipment_types or [],
                    tags=tags or [],
                    file_size=file_size,
                    file_checksum=file_checksum
                )
                
                session.add(master_form)
                session.flush()  # Get the ID
                
                # Create initial version
                form_version = FormVersion(
                    master_form_id=master_form.id,
                    version=version,
                    xml_content=xml_content,
                    is_current=True,
                    is_published=True,
                    file_size=file_size,
                    file_checksum=file_checksum,
                    created_by=created_by,
                    change_summary="Initial version"
                )
                
                session.add(form_version)
                session.commit()
                session.refresh(master_form)
                
                logger.info(f"Created master form: {name} v{version}")
                return master_form
                
        except Exception as e:
            logger.error(f"Master form creation failed: {str(e)}")
            return None
    
    def create_customization_request(self, client_name: str, form_title: str,
                                   master_form_id: int, raw_request: str,
                                   created_by: int) -> Optional[CustomizationRequest]:
        """Create new customization request"""
        try:
            with self.db_manager.get_session() as session:
                request_id = f"req_{generate_uuid()[:8]}"
                
                request = CustomizationRequest(
                    request_id=request_id,
                    client_name=client_name,
                    form_title=form_title,
                    master_form_id=master_form_id,
                    raw_request=raw_request,
                    created_by=created_by
                )
                
                session.add(request)
                session.commit()
                session.refresh(request)
                
                logger.info(f"Created customization request: {request_id}")
                return request
                
        except Exception as e:
            logger.error(f"Customization request creation failed: {str(e)}")
            return None

class OperationLogger:
    """Log all form operations for audit trail"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def log_operation(self, operation_type: OperationType, description: str,
                     target_type: str, target_id: str = None, target_name: str = None,
                     user_id: int = None, success: bool = True,
                     before_data: Dict = None, after_data: Dict = None,
                     **kwargs) -> Optional[FormOperation]:
        """Log form operation"""
        try:
            with self.db_manager.get_session() as session:
                operation_id = f"op_{generate_uuid()[:8]}"
                
                operation = FormOperation(
                    operation_id=operation_id,
                    operation_type=operation_type.value,
                    operation_description=description,
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name,
                    user_id=user_id,
                    success=success,
                    before_data=before_data,
                    after_data=after_data,
                    completed_at=datetime.utcnow(),
                    **kwargs
                )
                
                session.add(operation)
                session.commit()
                
                return operation
                
        except Exception as e:
            logger.error(f"Operation logging failed: {str(e)}")
            return None

# Global database manager instance
db_manager = None

def get_db_manager() -> DatabaseManager:
    """Get global database manager instance"""
    global db_manager
    if db_manager is None:
        # Use environment variable or default to SQLite
        database_url = os.getenv('DATABASE_URL', 'sqlite:///./de4_forms_platform.db')
        db_manager = DatabaseManager(database_url)
    return db_manager

def initialize_database(force_recreate: bool = False) -> bool:
    """Initialize the database"""
    manager = get_db_manager()
    return manager.initialize_database(force_recreate)

# Convenience functions
def get_user_manager() -> UserManager:
    """Get user manager instance"""
    return UserManager(get_db_manager())

def get_form_manager() -> FormManager:
    """Get form manager instance"""
    return FormManager(get_db_manager())

def get_operation_logger() -> OperationLogger:
    """Get operation logger instance"""
    return OperationLogger(get_db_manager())

# Export main components
__all__ = [
    'DatabaseManager', 'UserManager', 'FormManager', 'OperationLogger',
    'get_db_manager', 'get_user_manager', 'get_form_manager', 'get_operation_logger',
    'initialize_database'
]
