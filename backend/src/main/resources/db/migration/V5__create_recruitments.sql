CREATE TABLE recruitments (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES companies (id),
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('DRAFT', 'PUBLISHED', 'IN_PROGRESS', 'CLOSED')),
    current_stage_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE,
    closed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX recruitments_company_idx ON recruitments (company_id, created_at DESC);

CREATE TABLE stages (
    id UUID PRIMARY KEY,
    recruitment_id UUID NOT NULL REFERENCES recruitments (id),
    seq INT NOT NULL,
    name VARCHAR(50) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('DOCUMENT', 'ASSESSMENT', 'INTERVIEW')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('PENDING', 'ACTIVE', 'CONFIRMED', 'DONE')),
    confirmed_at TIMESTAMP WITH TIME ZONE,
    confirmed_by UUID,
    done_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT stages_recruitment_seq_key UNIQUE (recruitment_id, seq)
);
