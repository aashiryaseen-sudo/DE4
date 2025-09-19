-- DE4 Forms Platform - Performance Indexes
-- Run this script to add indexes for better dashboard performance

-- Index for form_versions created_at (most important for dashboard)
CREATE INDEX IF NOT EXISTS idx_form_versions_created_at_desc ON form_versions(created_at DESC);

-- Index for form_operations started_at (for operations table)
CREATE INDEX IF NOT EXISTS idx_form_operations_started_at_desc ON form_operations(started_at DESC);

-- Index for customization_requests created_at (for user prompts table)
CREATE INDEX IF NOT EXISTS idx_customization_requests_created_at_desc ON customization_requests(created_at DESC);

-- Index for user_sessions last_activity (for active sessions table)
CREATE INDEX IF NOT EXISTS idx_user_sessions_last_activity_desc ON user_sessions(last_activity DESC);

-- Index for master_forms created_at (for master forms table)
CREATE INDEX IF NOT EXISTS idx_master_forms_created_at_desc ON master_forms(created_at DESC);

-- Composite index for form_versions with master_form_id and created_at
CREATE INDEX IF NOT EXISTS idx_form_versions_master_created ON form_versions(master_form_id, created_at DESC);

-- Index for form_operations success flag (for success/failed counts)
CREATE INDEX IF NOT EXISTS idx_form_operations_success ON form_operations(success);

-- Display success message
SELECT 'Performance indexes added successfully!' as status;
