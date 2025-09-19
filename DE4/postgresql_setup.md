# PostgreSQL Database Setup for DE4 Platform

## 1. Create Database and User

```sql
-- Connect to PostgreSQL as superuser (postgres)
-- Create database
CREATE DATABASE de4_forms_platform;

-- Create user for the application
CREATE USER de4_user WITH PASSWORD 'your_secure_password_here';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE de4_forms_platform TO de4_user;

-- Connect to the de4_forms_platform database
\c de4_forms_platform

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO de4_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO de4_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO de4_user;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO de4_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO de4_user;
```

## 2. Environment Variables

Create a `.env` file in your project root with these variables:

```env
# Database Configuration
DATABASE_URL=postgresql://de4_user:your_secure_password_here@localhost:5432/de4_forms_platform
DB_HOST=localhost
DB_PORT=5432
DB_NAME=de4_forms_platform
DB_USER=de4_user
DB_PASSWORD=your_secure_password_here

# Application Settings
SECRET_KEY=your_super_secret_key_here
ENVIRONMENT=development
DEBUG=True

# File Storage
UPLOAD_FOLDER=uploads
MASTER_FORMS_FOLDER=master_forms
MAX_FILE_SIZE=50MB

# Session Settings
SESSION_EXPIRE_HOURS=24
MAX_SESSIONS_PER_USER=5

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/de4_platform.log
```

## 3. Required PostgreSQL Extensions

```sql
-- Connect to de4_forms_platform database
\c de4_forms_platform

-- Enable UUID extension for generating UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable full-text search (optional, for advanced search features)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Enable JSON operators (should be available by default in modern PostgreSQL)
-- CREATE EXTENSION IF NOT EXISTS "jsonb_plperl";
```

## 4. Create Tables (Run the SQL script)

Use the provided `create_tables.sql` script to create all required tables.

## 5. Initial Data Setup

After creating tables, run the seed script to populate initial data:

```bash
python seed_database.py
```

## 6. Verify Setup

```sql
-- Check if all tables are created
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Check user permissions
SELECT grantee, privilege_type 
FROM information_schema.role_table_grants 
WHERE table_schema = 'public' AND grantee = 'de4_user';

-- Test data
SELECT COUNT(*) as user_count FROM users;
SELECT COUNT(*) as master_forms_count FROM master_forms;
```

## 7. Performance Optimization (Optional)

```sql
-- Add additional indexes for better performance
CREATE INDEX CONCURRENTLY idx_users_email_lower ON users (LOWER(email));
CREATE INDEX CONCURRENTLY idx_form_operations_timestamp ON form_operations (started_at DESC);
CREATE INDEX CONCURRENTLY idx_customization_requests_status_created ON customization_requests (status, created_at DESC);

-- Update table statistics
ANALYZE;
```

## 8. Backup Setup (Recommended)

```bash
# Create backup script
#!/bin/bash
BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/de4_backup_$DATE.sql"

pg_dump -h localhost -U de4_user -d de4_forms_platform > $BACKUP_FILE

# Keep only last 7 days of backups
find $BACKUP_DIR -name "de4_backup_*.sql" -mtime +7 -delete
```

## Connection Test

Test your connection with:

```python
from database_manager import get_db_manager

# This will test the connection
db_manager = get_db_manager()
health = db_manager.health_check()
print(health)
```
