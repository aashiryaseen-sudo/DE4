-- DE4 Forms Platform - PostgreSQL Table Creation Script
-- Run this script after creating the database and user

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create ENUM types
CREATE TYPE user_role AS ENUM ('admin', 'manager', 'editor', 'viewer');
CREATE TYPE request_status AS ENUM ('pending', 'in_progress', 'ready_for_review', 'under_review', 'revision_requested', 'approved', 'deployed', 'cancelled');
CREATE TYPE operation_type AS ENUM ('create', 'read', 'update', 'delete', 'clone', 'deploy');
CREATE TYPE session_status AS ENUM ('active', 'expired', 'terminated');

-- =============== USER MANAGEMENT TABLES ===============

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(200),
    role user_role NOT NULL DEFAULT 'viewer',
    
    -- Profile info
    company VARCHAR(200),
    department VARCHAR(100),
    phone VARCHAR(20),
    
    -- Account status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    last_login TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- User sessions table
CREATE TABLE user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    
    -- Session details
    ip_address INET,
    user_agent TEXT,
    device_info JSONB,
    
    -- Session management
    status session_status NOT NULL DEFAULT 'active',
    expires_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    terminated_at TIMESTAMP
);

-- =============== FORM MANAGEMENT TABLES ===============

-- Master forms table
CREATE TABLE master_forms (
    id SERIAL PRIMARY KEY,
    form_id VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    
    -- Version management
    current_version VARCHAR(100) NOT NULL,
    version_count INTEGER NOT NULL DEFAULT 1,
    
    -- Form metadata
    form_type VARCHAR(50),
    client_category VARCHAR(100),
    equipment_types JSONB,
    tags JSONB,
    
    -- Status and visibility
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_template BOOLEAN NOT NULL DEFAULT TRUE,
    access_level VARCHAR(20) NOT NULL DEFAULT 'public',
    
    -- Statistics
    usage_count INTEGER NOT NULL DEFAULT 0,
    field_count INTEGER NOT NULL DEFAULT 0,
    section_count INTEGER NOT NULL DEFAULT 0,
    
    -- File info
    file_size INTEGER,
    file_checksum VARCHAR(64),
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Form versions table
CREATE TABLE form_versions (
    id SERIAL PRIMARY KEY,
    master_form_id INTEGER NOT NULL REFERENCES master_forms(id) ON DELETE CASCADE,
    version VARCHAR(100) NOT NULL,
    
    -- Version details
    version_notes TEXT,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- XML Content
    xml_content TEXT NOT NULL,
    xml_compressed BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Form structure metadata
    form_structure JSONB,
    field_names JSONB,
    choice_lists JSONB,
    
    -- File information
    file_path VARCHAR(500),
    file_size INTEGER,
    file_checksum VARCHAR(64),
    
    -- Version metadata
    created_by INTEGER REFERENCES users(id),
    change_summary TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    UNIQUE(master_form_id, version)
);

-- =============== CUSTOMIZATION SYSTEM TABLES ===============

-- Customization requests table
CREATE TABLE customization_requests (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Request details
    client_name VARCHAR(200) NOT NULL,
    form_title VARCHAR(200) NOT NULL,
    master_form_id INTEGER NOT NULL REFERENCES master_forms(id),
    
    -- Request content
    raw_request TEXT NOT NULL,
    parsed_requirements JSONB,
    
    -- Equipment selection
    selected_equipment_types JSONB,
    excluded_equipment_types JSONB,
    
    -- Customizations
    field_additions JSONB,
    field_removals JSONB,
    field_modifications JSONB,
    choice_modifications JSONB,
    
    -- Workflow management
    status request_status NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 3,
    
    -- Assignment and review
    created_by INTEGER NOT NULL REFERENCES users(id),
    assigned_to INTEGER REFERENCES users(id),
    reviewed_by INTEGER REFERENCES users(id),
    
    -- Processing details
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP,
    processing_time_seconds FLOAT,
    
    -- Output
    generated_form_path VARCHAR(500),
    generated_form_version_id INTEGER REFERENCES form_versions(id),
    
    -- Quality and feedback
    quality_score FLOAT,
    review_notes JSONB,
    feedback_summary TEXT,
    
    -- Metrics
    iteration_count INTEGER NOT NULL DEFAULT 0,
    customizations_applied INTEGER NOT NULL DEFAULT 0,
    errors_encountered JSONB,
    warnings_generated JSONB,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============== AUDIT AND OPERATIONS TABLE ===============

-- Form operations table
CREATE TABLE form_operations (
    id SERIAL PRIMARY KEY,
    operation_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Operation details
    operation_type operation_type NOT NULL,
    operation_description VARCHAR(500) NOT NULL,
    
    -- Target information
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(100),
    target_name VARCHAR(200),
    
    -- Form context
    master_form_id INTEGER REFERENCES master_forms(id),
    form_version_id INTEGER REFERENCES form_versions(id),
    customization_request_id INTEGER REFERENCES customization_requests(id),
    
    -- Operation context
    user_id INTEGER NOT NULL REFERENCES users(id),
    session_id INTEGER REFERENCES user_sessions(id),
    
    -- Operation data
    before_data JSONB,
    after_data JSONB,
    operation_parameters JSONB,
    
    -- Result information
    success BOOLEAN NOT NULL,
    error_message TEXT,
    warnings JSONB,
    
    -- Performance metrics
    execution_time_ms INTEGER,
    memory_usage_mb FLOAT,
    
    -- Client information
    ip_address INET,
    user_agent VARCHAR(500),
    
    -- Timestamps
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- =============== INDEXES FOR PERFORMANCE ===============

-- User indexes
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_active ON users(is_active);

-- Session indexes
CREATE INDEX idx_user_sessions_token ON user_sessions(session_token);
CREATE INDEX idx_user_sessions_user_status ON user_sessions(user_id, status);
CREATE INDEX idx_user_sessions_expiry ON user_sessions(expires_at);
CREATE INDEX idx_user_sessions_last_activity ON user_sessions(last_activity);

-- Master form indexes
CREATE INDEX idx_master_forms_form_id ON master_forms(form_id);
CREATE INDEX idx_master_forms_name ON master_forms(name);
CREATE INDEX idx_master_forms_type ON master_forms(form_type);
CREATE INDEX idx_master_forms_active ON master_forms(is_active);
CREATE INDEX idx_master_forms_template ON master_forms(is_template);
CREATE INDEX idx_master_forms_created_at ON master_forms(created_at);

-- Form version indexes
CREATE INDEX idx_form_versions_master_form ON form_versions(master_form_id);
CREATE INDEX idx_form_versions_current ON form_versions(master_form_id, is_current);
CREATE INDEX idx_form_versions_published ON form_versions(is_published);
CREATE INDEX idx_form_versions_created_at ON form_versions(created_at);

-- Customization request indexes
CREATE INDEX idx_customization_requests_request_id ON customization_requests(request_id);
CREATE INDEX idx_customization_requests_status ON customization_requests(status);
CREATE INDEX idx_customization_requests_created_by ON customization_requests(created_by);
CREATE INDEX idx_customization_requests_assigned_to ON customization_requests(assigned_to);
CREATE INDEX idx_customization_requests_priority ON customization_requests(priority);
CREATE INDEX idx_customization_requests_created_at ON customization_requests(created_at);
CREATE INDEX idx_customization_requests_master_form ON customization_requests(master_form_id);

-- Form operations indexes
CREATE INDEX idx_form_operations_operation_id ON form_operations(operation_id);
CREATE INDEX idx_form_operations_type ON form_operations(operation_type);
CREATE INDEX idx_form_operations_user ON form_operations(user_id);
CREATE INDEX idx_form_operations_target ON form_operations(target_type, target_id);
CREATE INDEX idx_form_operations_timestamp ON form_operations(started_at);
CREATE INDEX idx_form_operations_success ON form_operations(success);
CREATE INDEX idx_form_operations_master_form ON form_operations(master_form_id);
CREATE INDEX idx_form_operations_request ON form_operations(customization_request_id);

-- JSONB indexes for better JSON query performance
CREATE INDEX idx_master_forms_equipment_types_gin ON master_forms USING GIN(equipment_types);
CREATE INDEX idx_master_forms_tags_gin ON master_forms USING GIN(tags);
CREATE INDEX idx_form_versions_structure_gin ON form_versions USING GIN(form_structure);
CREATE INDEX idx_customization_requests_requirements_gin ON customization_requests USING GIN(parsed_requirements);

-- =============== TRIGGERS FOR UPDATED_AT ===============

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables with updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_master_forms_updated_at BEFORE UPDATE ON master_forms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_customization_requests_updated_at BEFORE UPDATE ON customization_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============== VIEWS FOR COMMON QUERIES ===============

-- Active forms view
CREATE VIEW active_master_forms AS
SELECT 
    mf.*,
    fv.xml_content,
    fv.form_structure,
    (SELECT COUNT(*) FROM customization_requests cr WHERE cr.master_form_id = mf.id) as request_count
FROM master_forms mf
LEFT JOIN form_versions fv ON mf.id = fv.master_form_id AND fv.is_current = TRUE
WHERE mf.is_active = TRUE;

-- Recent requests view
CREATE VIEW recent_customization_requests AS
SELECT 
    cr.*,
    mf.name as master_form_name,
    u.username as created_by_username,
    u.full_name as created_by_name
FROM customization_requests cr
JOIN master_forms mf ON cr.master_form_id = mf.id
JOIN users u ON cr.created_by = u.id
ORDER BY cr.created_at DESC;

-- User activity view
CREATE VIEW user_activity_summary AS
SELECT 
    u.id,
    u.username,
    u.full_name,
    u.last_login,
    COUNT(DISTINCT us.id) as active_sessions,
    COUNT(DISTINCT cr.id) as total_requests,
    COUNT(DISTINCT fo.id) as total_operations
FROM users u
LEFT JOIN user_sessions us ON u.id = us.user_id AND us.status = 'active'
LEFT JOIN customization_requests cr ON u.id = cr.created_by
LEFT JOIN form_operations fo ON u.id = fo.user_id
WHERE u.is_active = TRUE
GROUP BY u.id, u.username, u.full_name, u.last_login;

-- =============== INITIAL DATA CONSTRAINTS ===============

-- Ensure at least one admin user exists (will be handled by seed script)
-- Ensure form versions consistency
ALTER TABLE form_versions ADD CONSTRAINT check_current_version_published 
    CHECK (NOT is_current OR is_published);

-- Ensure valid priority values
ALTER TABLE customization_requests ADD CONSTRAINT check_priority_range 
    CHECK (priority >= 1 AND priority <= 5);

-- Ensure valid quality scores
ALTER TABLE customization_requests ADD CONSTRAINT check_quality_score_range 
    CHECK (quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100));

COMMIT;

-- Display success message
SELECT 'DE4 Forms Platform database tables created successfully!' as status;
