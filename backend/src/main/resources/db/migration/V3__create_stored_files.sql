CREATE TABLE stored_files (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES companies (id),
    original_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    storage_key VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX stored_files_company_idx ON stored_files (company_id);
