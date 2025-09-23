#!/usr/bin/env python3
"""
Database optimization script for DE4 Forms
Adds indexes to improve dashboard query performance
"""

import os
import sys
from sqlalchemy import create_engine, text
from database_schema import DatabaseConfig

def optimize_database():
    """Add database indexes for better performance"""
    try:
        # Get database URL from environment
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL environment variable not set")
            return False
            
        # Create engine
        engine = create_engine(database_url)
        
        # Indexes to add
        indexes = [
            # FormVersion indexes
            "CREATE INDEX IF NOT EXISTS idx_form_versions_created_at ON form_versions(created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_form_versions_master_form_id ON form_versions(master_form_id);",
            "CREATE INDEX IF NOT EXISTS idx_form_versions_is_current ON form_versions(is_current);",
            
            # MasterForm indexes
            "CREATE INDEX IF NOT EXISTS idx_master_forms_created_at ON master_forms(created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_master_forms_name ON master_forms(name);",
            
            # CustomizationRequest indexes
            "CREATE INDEX IF NOT EXISTS idx_customization_requests_created_at ON customization_requests(created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_customization_requests_master_form_id ON customization_requests(master_form_id);",
            "CREATE INDEX IF NOT EXISTS idx_customization_requests_status ON customization_requests(status);",
            
            # FormOperation indexes
            "CREATE INDEX IF NOT EXISTS idx_form_operations_started_at ON form_operations(started_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_form_operations_user_id ON form_operations(user_id);",
            
            # UserSession indexes
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_last_activity ON user_sessions(last_activity DESC);",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);",
        ]
        
        print("🔧 Adding database indexes for better performance...")
        
        with engine.connect() as conn:
            for index_sql in indexes:
                try:
                    conn.execute(text(index_sql))
                    print(f"✅ Created index: {index_sql.split('idx_')[1].split(' ')[0]}")
                except Exception as e:
                    print(f"⚠️  Index might already exist: {e}")
            
            conn.commit()
        
        print("✅ Database optimization completed!")
        return True
        
    except Exception as e:
        print(f"❌ Database optimization failed: {e}")
        return False

if __name__ == "__main__":
    success = optimize_database()
    sys.exit(0 if success else 1)
