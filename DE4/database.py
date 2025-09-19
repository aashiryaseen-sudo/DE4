"""
DE4 Database Connection and Dependencies
FastAPI database integration and session management
"""

from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from database_manager import get_db_manager, get_user_manager, get_form_manager, get_operation_logger
from database_schema import User, UserSession, SessionStatus
import logging

logger = logging.getLogger(__name__)

# Global database manager instance
db_manager = get_db_manager()

def get_database_session() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions"""
    session = db_manager.config.SessionLocal()
    try:
        yield session
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {str(e)}")
        raise
    finally:
        session.close()

def get_current_user(
    session_token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    db: Session = Depends(get_database_session)
) -> User:
    """FastAPI dependency to get current authenticated user"""
    # Prefer explicit session_token param, then X-Session-Token header, then Authorization: Bearer <token>
    token_to_validate: Optional[str] = session_token or x_session_token
    
    if not token_to_validate and authorization:
        try:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() == "bearer" and token:
                token_to_validate = token
        except Exception:
            pass
    
    if not token_to_validate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token required"
        )
    
    try:
        user_manager = get_user_manager()
        user = user_manager.validate_session(token_to_validate)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session"
            )
        
        return user
        
    except Exception as e:
        logger.error(f"User authentication failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error"
        )

def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """FastAPI dependency to get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )
    return current_user

def get_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """FastAPI dependency to ensure admin privileges"""
    from database_schema import UserRole
    
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user

def require_editor_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Require role editor/manager/admin"""
    from database_schema import UserRole as UR
    role_value = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if role_value not in {UR.EDITOR.value, UR.MANAGER.value, UR.ADMIN.value}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editor or higher privileges required"
        )
    return current_user

# Initialize database on module load
def initialize_database():
    """Initialize database with tables and default data"""
    try:
        success = db_manager.initialize_database()
        if success:
            logger.info("Database initialized successfully")
        else:
            logger.error("Database initialization failed")
        return success
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        return False

# Export dependencies and utilities
__all__ = [
    'get_database_session',
    'get_current_user', 
    'get_current_active_user',
    'get_admin_user',
    'require_editor_user',
    'initialize_database',
    'db_manager'
]
