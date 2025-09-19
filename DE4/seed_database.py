"""
DE4 Database Seeding Script
Populate database with initial data and existing master forms
"""

import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any
import hashlib
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from database_manager import (
    get_db_manager, get_user_manager, get_form_manager,
    initialize_database
)
from database_schema import UserRole
from xml_parser import XLSFormParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseSeeder:
    """Database seeding utility"""
    
    def __init__(self):
        self.db_manager = get_db_manager()
        self.user_manager = get_user_manager()
        self.form_manager = get_form_manager()
        self.master_forms_dir = project_root / "master_forms"
    
    def seed_all(self):
        """Run complete database seeding"""
        logger.info("Starting database seeding...")
        
        try:
            # Initialize database
            if not initialize_database():
                logger.error("Failed to initialize database")
                return False
            
            # Seed users
            self.seed_users()
            
            # Seed master forms
            self.seed_master_forms()
            
            # Verify seeding
            self.verify_seeding()
            
            logger.info("Database seeding completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Database seeding failed: {str(e)}")
            return False
    
    def seed_users(self):
        """Create initial users"""
        logger.info("Seeding users...")
        
        users_to_create = [
            {
                "username": "admin",
                "email": "admin@de4platform.com",
                "password": "admin123",  # Change in production!
                "full_name": "System Administrator",
                "role": UserRole.ADMIN,
                "company": "DE4 Platform",
                "is_verified": True
            },
            {
                "username": "manager",
                "email": "manager@de4platform.com", 
                "password": "manager123",
                "full_name": "Form Manager",
                "role": UserRole.MANAGER,
                "company": "DE4 Platform",
                "is_verified": True
            },
            {
                "username": "editor",
                "email": "editor@de4platform.com",
                "password": "editor123", 
                "full_name": "Form Editor",
                "role": UserRole.EDITOR,
                "company": "DE4 Platform",
                "is_verified": True
            },
            {
                "username": "demo_user",
                "email": "demo@example.com",
                "password": "demo123",
                "full_name": "Demo User",
                "role": UserRole.VIEWER,
                "company": "Demo Company",
                "is_verified": True
            }
        ]
        
        created_count = 0
        for user_data in users_to_create:
            user = self.user_manager.create_user(**user_data)
            if user:
                created_count += 1
                logger.info(f"Created user: {user.username} ({user.role.value})")
            else:
                logger.warning(f"User already exists or creation failed: {user_data['username']}")
        
        logger.info(f"Created {created_count} users")
    
    def seed_master_forms(self):
        """Import existing master forms from master_forms directory"""
        logger.info("Seeding master forms...")
        
        if not self.master_forms_dir.exists():
            logger.warning(f"Master forms directory not found: {self.master_forms_dir}")
            return
        
        xml_files = list(self.master_forms_dir.glob("*.xml"))
        if not xml_files:
            logger.warning("No XML files found in master_forms directory")
            return
        
        logger.info(f"Found {len(xml_files)} XML files to import")
        
        created_count = 0
        for xml_file in xml_files:
            try:
                if self.import_master_form(xml_file):
                    created_count += 1
            except Exception as e:
                logger.error(f"Failed to import {xml_file.name}: {str(e)}")
        
        logger.info(f"Successfully imported {created_count} master forms")
    
    def import_master_form(self, xml_file_path: Path) -> bool:
        """Import a single master form from XML file"""
        try:
            # Read XML content
            with open(xml_file_path, 'r', encoding='utf-8') as f:
                xml_content = f.read()
            
            # Parse form to extract metadata
            parser = XLSFormParser(str(xml_file_path))
            
            # Extract form name and version from filename or content
            filename = xml_file_path.stem
            form_name = self.extract_form_name(filename)
            version = self.extract_version(filename)
            
            # Try to get more metadata from parsed form
            try:
                analysis = parser.analyze_complete_form()
                form_structure = analysis
                
                # Extract equipment types from survey fields
                survey_fields = parser.parse_survey_fields()
                equipment_types = self.extract_equipment_types(survey_fields)
                
                # Count fields and sections
                field_count = len(survey_fields)
                section_count = len([f for f in survey_fields if f.get('type') in ['begin group', 'begin repeat']])
                
            except Exception as e:
                logger.warning(f"Could not parse form structure for {filename}: {str(e)}")
                equipment_types = []
                field_count = 0
                section_count = 0
            
            # Determine form type and tags from filename
            form_type, tags = self.categorize_form(filename)
            
            # Get admin user ID for created_by
            with self.db_manager.get_session() as session:
                from database_schema import User
                admin_user = session.query(User).filter(User.role == UserRole.ADMIN).first()
                created_by = admin_user.id if admin_user else None
            
            # Create master form
            master_form = self.form_manager.create_master_form(
                name=form_name,
                version=version,
                xml_content=xml_content,
                description=f"Imported master form: {form_name}",
                form_type=form_type,
                equipment_types=equipment_types,
                tags=tags,
                created_by=created_by
            )
            
            if master_form:
                # Update additional metadata
                with self.db_manager.get_session() as session:
                    form = session.query(self.db_manager.config.SessionLocal().query(master_form.__class__)).filter_by(id=master_form.id).first()
                    if form:
                        form.field_count = field_count
                        form.section_count = section_count
                        session.commit()
                
                logger.info(f"Imported master form: {form_name} v{version}")
                return True
            else:
                logger.warning(f"Failed to create master form: {form_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error importing {xml_file_path}: {str(e)}")
            return False
    
    def extract_form_name(self, filename: str) -> str:
        """Extract clean form name from filename"""
        # Remove common prefixes/suffixes
        name = filename.replace('edited_', '').replace('modified_', '')
        
        # Split by common separators and take meaningful parts
        parts = name.replace('-', ' ').replace('_', ' ').split()
        
        # Remove version-like parts
        cleaned_parts = []
        for part in parts:
            # Skip parts that look like versions or timestamps
            if not (part.lower().startswith('v') or 
                   part.lower().startswith('20') or
                   part.isdigit() or
                   '.' in part):
                cleaned_parts.append(part)
        
        return ' '.join(cleaned_parts[:4])  # Limit to first 4 meaningful parts
    
    def extract_version(self, filename: str) -> str:
        """Extract version from filename"""
        import re
        
        # Look for version patterns
        version_patterns = [
            r'[vV](\d+\.\d+(?:\.\d+)?)',  # v1.0, V1.2.3
            r'(\d{4}[vV]\d+\.\d+)',       # 2025v1.3
            r'(\d+\.\d+(?:\.\d+)?)',      # 1.0, 1.2.3
        ]
        
        for pattern in version_patterns:
            match = re.search(pattern, filename)
            if match:
                return match.group(1)
        
        return "1.0"  # Default version
    
    def extract_equipment_types(self, survey_fields: List[Dict]) -> List[str]:
        """Extract equipment types from survey fields"""
        equipment_types = set()
        
        common_equipment = [
            'boiler', 'chiller', 'pump', 'fan', 'hvac', 'package unit',
            'air handler', 'cooling tower', 'compressor', 'heat exchanger',
            'valve', 'damper', 'motor', 'generator', 'transformer'
        ]
        
        for field in survey_fields:
            field_name = field.get('name', '').lower()
            field_label = field.get('label', '').lower()
            field_text = f"{field_name} {field_label}"
            
            for equipment in common_equipment:
                if equipment in field_text:
                    equipment_types.add(equipment.title())
        
        return list(equipment_types)
    
    def categorize_form(self, filename: str) -> tuple:
        """Categorize form and generate tags based on filename"""
        filename_lower = filename.lower()
        
        # Determine form type
        if 'pm' in filename_lower or 'preventive' in filename_lower:
            form_type = "Preventive Maintenance"
        elif 'hvac' in filename_lower:
            form_type = "HVAC"
        elif 'startup' in filename_lower or 'commissioning' in filename_lower:
            form_type = "Commissioning"
        elif 'inspection' in filename_lower:
            form_type = "Inspection"
        elif 'iot' in filename_lower or 'tech' in filename_lower:
            form_type = "Technology"
        else:
            form_type = "General"
        
        # Generate tags
        tags = []
        tag_keywords = {
            'maintenance': ['pm', 'maintenance', 'service'],
            'hvac': ['hvac', 'air', 'cooling', 'heating'],
            'inspection': ['inspection', 'check', 'verify'],
            'startup': ['startup', 'commissioning', 'verification'],
            'iot': ['iot', 'tech', 'digital'],
            'commercial': ['commercial', 'building'],
            'industrial': ['industrial', 'plant', 'facility']
        }
        
        for tag, keywords in tag_keywords.items():
            if any(keyword in filename_lower for keyword in keywords):
                tags.append(tag)
        
        return form_type, tags
    
    def verify_seeding(self):
        """Verify that seeding was successful"""
        logger.info("Verifying database seeding...")
        
        health = self.db_manager.health_check()
        if health['status'] == 'healthy':
            stats = health['stats']
            logger.info(f"Database health: {health['status']}")
            logger.info(f"Users: {stats['users']}")
            logger.info(f"Master forms: {stats['master_forms']}")
            logger.info(f"Active master forms: {stats['active_master_forms']}")
            logger.info(f"Form versions: {stats['form_versions']}")
        else:
            logger.error(f"Database health check failed: {health.get('error', 'Unknown error')}")

def main():
    """Main seeding function"""
    seeder = DatabaseSeeder()
    success = seeder.seed_all()
    
    if success:
        logger.info("✅ Database seeding completed successfully!")
        sys.exit(0)
    else:
        logger.error("❌ Database seeding failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
