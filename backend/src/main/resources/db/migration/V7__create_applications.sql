CREATE TABLE applications (
    id UUID PRIMARY KEY,
    recruitment_id UUID NOT NULL REFERENCES recruitments (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    posting_id UUID NOT NULL REFERENCES job_postings (id),
    application_no INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    certificates TEXT,
    consent_privacy BOOLEAN NOT NULL,
    consent_ai BOOLEAN NOT NULL,
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    analysis_status VARCHAR(20) NOT NULL CHECK (analysis_status IN ('PENDING', 'DONE', 'FAILED')),
    career_years INT,
    last_company VARCHAR(255),
    document_score INT,
    score_passed BOOLEAN NOT NULL DEFAULT FALSE,
    analyzed_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT applications_recruitment_email_key UNIQUE (recruitment_id, email),
    CONSTRAINT applications_recruitment_no_key UNIQUE (recruitment_id, application_no)
);

CREATE INDEX applications_recruitment_idx ON applications (recruitment_id, submitted_at DESC);

CREATE TABLE application_documents (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL REFERENCES applications (id),
    type VARCHAR(20) NOT NULL CHECK (type IN ('RESUME', 'COVER_LETTER', 'PORTFOLIO')),
    file_id UUID NOT NULL REFERENCES stored_files (id),
    file_name VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    text TEXT NOT NULL,
    CONSTRAINT application_documents_type_key UNIQUE (application_id, type)
);
