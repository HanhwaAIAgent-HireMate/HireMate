CREATE TABLE assessment_results (
    id UUID PRIMARY KEY,
    stage_id UUID NOT NULL REFERENCES stages (id),
    application_id UUID NOT NULL REFERENCES applications (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    total NUMERIC(7, 2),
    areas TEXT NOT NULL,
    grade VARCHAR(20),
    file_id UUID REFERENCES stored_files (id),
    file_name VARCHAR(255),
    url VARCHAR(500),
    note TEXT,
    source VARCHAR(20) NOT NULL,
    registered_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT assessment_results_stage_application_key UNIQUE (stage_id, application_id)
);
