#!/usr/bin/env python3
"""
Debug script to check form versions and their XML content
"""

import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_schema import FormVersion, MasterForm

def debug_form_versions():
    """Check what's in the form_versions table"""
    try:
        # Get database URL
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL environment variable not set")
            return False
            
        # Create engine and session
        engine = create_engine(database_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        print("🔍 Checking form versions in database...")
        
        # Get all form versions
        versions = session.query(FormVersion).order_by(FormVersion.created_at.desc()).limit(10).all()
        
        print(f"📊 Found {len(versions)} form versions:")
        
        for i, version in enumerate(versions, 1):
            print(f"\n--- Version {i} ---")
            print(f"ID: {version.id}")
            print(f"Master Form ID: {version.master_form_id}")
            print(f"Version: {version.version}")
            print(f"Created By: {version.created_by}")
            print(f"Created At: {version.created_at}")
            print(f"XML Content Length: {len(version.xml_content) if version.xml_content else 0}")
            print(f"Has XML Content: {bool(version.xml_content and len(version.xml_content.strip()) > 0)}")
            
            if version.xml_content:
                print(f"XML Preview: {version.xml_content[:100]}...")
            else:
                print("XML Content: None or Empty")
                
            # Check master form
            if version.master_form_id:
                master = session.query(MasterForm).filter(MasterForm.id == version.master_form_id).first()
                if master:
                    print(f"Master Form Name: {master.name}")
                else:
                    print("Master Form: Not found")
        
        session.close()
        print("\n✅ Debug completed!")
        return True
        
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = debug_form_versions()
    sys.exit(0 if success else 1)
