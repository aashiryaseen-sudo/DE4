#!/usr/bin/env python3
"""
Check Form Versions in Database
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

try:
    from database_manager import get_db_manager
    from database_schema import FormVersion
    
    print("🔍 Checking form versions in database...")
    
    db_manager = get_db_manager()
    with db_manager.get_session() as session:
        versions = session.query(FormVersion).order_by(FormVersion.created_at.desc()).limit(10).all()
        
        print(f"📊 Found {len(versions)} form versions:")
        print("-" * 80)
        
        for v in versions:
            xml_len = len(v.xml_content) if v.xml_content else 0
            has_content = "✅" if xml_len > 0 else "❌"
            print(f"{has_content} ID: {v.id:3d} | Version: {v.version:30s} | XML Length: {xml_len:6d} | Created: {v.created_at}")
        
        print("-" * 80)
        print(f"📈 Summary: {sum(1 for v in versions if len(v.xml_content or '') > 0)}/{len(versions)} versions have XML content")
        
except Exception as e:
    print(f"❌ Error: {str(e)}")
    sys.exit(1)
