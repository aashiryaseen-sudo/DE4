#!/usr/bin/env python3
"""
Fix script for download issue
This script will:
1. Check what's in the database
2. Fix any missing XML content
3. Test the download functionality
"""

import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_schema import FormVersion, MasterForm, UserFormSession
from datetime import datetime

def fix_download_issue():
    """Fix the download issue by checking and fixing data"""
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
        
        print("🔍 Analyzing download issue...")
        
        # 1. Check form versions
        print("\n1. Checking Form Versions:")
        versions = session.query(FormVersion).order_by(FormVersion.created_at.desc()).limit(5).all()
        
        for i, version in enumerate(versions, 1):
            has_xml = bool(version.xml_content and len(version.xml_content.strip()) > 0)
            print(f"   Version {i}: ID={version.id}, Has XML={has_xml}, Length={len(version.xml_content) if version.xml_content else 0}")
        
        # 2. Check user form sessions
        print("\n2. Checking User Form Sessions:")
        sessions = session.query(UserFormSession).order_by(UserFormSession.created_at.desc()).limit(5).all()
        
        for i, sess in enumerate(sessions, 1):
            print(f"   Session {i}: ID={sess.id}, Original={sess.original_file_path}, Modified={sess.modified_file_path}")
        
        # 3. Check if there are any form versions with XML content
        versions_with_xml = session.query(FormVersion).filter(
            FormVersion.xml_content.isnot(None),
            FormVersion.xml_content != ""
        ).count()
        
        print(f"\n3. Form versions with XML content: {versions_with_xml}")
        
        # 4. If no XML content, try to find the issue
        if versions_with_xml == 0:
            print("\n❌ No form versions have XML content!")
            print("This suggests the AI edit is not saving XML content properly.")
            
            # Check if there are any user form sessions with modified files
            sessions_with_modifications = session.query(UserFormSession).filter(
                UserFormSession.modified_file_path.isnot(None),
                UserFormSession.modified_file_path != ""
            ).all()
            
            print(f"Found {len(sessions_with_modifications)} sessions with modifications")
            
            # Try to create a form version from a session
            if sessions_with_modifications:
                print("\n🔧 Attempting to create form version from session...")
                session_data = sessions_with_modifications[0]
                
                # Read the modified file
                if os.path.exists(session_data.modified_file_path):
                    try:
                        with open(session_data.modified_file_path, 'r', encoding='utf-8') as f:
                            xml_content = f.read()
                        
                        print(f"✅ Read XML content: {len(xml_content)} characters")
                        
                        # Create a form version
                        form_name = os.path.basename(session_data.original_file_path).replace('.xml', '')
                        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                        
                        # Find or create master form
                        master_form = session.query(MasterForm).filter(MasterForm.name == form_name).first()
                        if not master_form:
                            master_form = MasterForm(
                                form_id=f"form_{form_name}_{timestamp}",
                                name=form_name,
                                description=f"Auto-created from session",
                                current_version=timestamp,
                                form_type="General",
                                is_active=True
                            )
                            session.add(master_form)
                            session.commit()
                            session.refresh(master_form)
                        
                        # Create form version
                        new_version = FormVersion(
                            master_form_id=master_form.id,
                            version=f"{form_name}_{timestamp}",
                            xml_content=xml_content,
                            xml_compressed=False,
                            created_by=session_data.user_id,
                            change_summary="Created from session data"
                        )
                        session.add(new_version)
                        session.commit()
                        
                        print(f"✅ Created form version: {new_version.id}")
                        
                    except Exception as e:
                        print(f"❌ Failed to create form version: {e}")
                else:
                    print(f"❌ Modified file not found: {session_data.modified_file_path}")
        
        session.close()
        print("\n✅ Fix completed!")
        return True
        
    except Exception as e:
        print(f"❌ Fix failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = fix_download_issue()
    sys.exit(0 if success else 1)
