ALTER TABLE companies
    ADD COLUMN intro TEXT NOT NULL DEFAULT '',
    ADD COLUMN culture TEXT NOT NULL DEFAULT '',
    ADD COLUMN talents TEXT NOT NULL DEFAULT '[]',
    ADD COLUMN benefits TEXT NOT NULL DEFAULT '[]',
    ADD COLUMN writing_style TEXT NOT NULL DEFAULT '',
    ADD COLUMN required_notices TEXT NOT NULL DEFAULT '[]';

CREATE TABLE notice_templates (
    company_id UUID NOT NULL REFERENCES companies (id),
    type VARCHAR(20) NOT NULL CHECK (type IN ('NEXT_STAGE', 'REJECT', 'FINAL_PASS', 'FINAL_REJECT')),
    subject VARCHAR(200) NOT NULL,
    greeting TEXT NOT NULL,
    ai_guide VARCHAR(200) NOT NULL,
    closing TEXT NOT NULL,
    required_text TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (company_id, type)
);

CREATE TABLE company_files (
    file_id UUID PRIMARY KEY REFERENCES stored_files (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    category VARCHAR(20) NOT NULL CHECK (category IN ('INTRO', 'POSTING')),
    name VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX company_files_company_idx ON company_files (company_id, category);
