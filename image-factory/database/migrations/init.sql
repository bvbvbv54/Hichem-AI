-- Initial database schema for ImageFactory
-- This is for reference; SQLAlchemy handles table creation automatically.

CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(36) PRIMARY KEY,
    type VARCHAR(32) NOT NULL DEFAULT 'single',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    prompt TEXT DEFAULT '',
    enhanced_prompt TEXT DEFAULT '',
    negative_prompt TEXT DEFAULT '',
    template_name VARCHAR(128) DEFAULT '',
    template_category VARCHAR(64) DEFAULT '',
    image_provider VARCHAR(32) DEFAULT 'replicate',
    model_name VARCHAR(128) DEFAULT '',
    width INTEGER DEFAULT 1024,
    height INTEGER DEFAULT 1024,
    num_images INTEGER DEFAULT 1,
    parameters JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    project_name VARCHAR(255) DEFAULT '',
    error_message TEXT DEFAULT '',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    progress REAL DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    parent_job_id VARCHAR(36),
    is_bulk_item BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs(parent_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_name);

CREATE TABLE IF NOT EXISTS assets (
    id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) DEFAULT '',
    file_path VARCHAR(512) NOT NULL,
    file_size INTEGER DEFAULT 0,
    mime_type VARCHAR(64) DEFAULT 'image/png',
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    alt_text TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    delivery_status VARCHAR(32) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assets_job_id ON assets(job_id);
