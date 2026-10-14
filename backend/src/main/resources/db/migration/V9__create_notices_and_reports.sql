ALTER TABLE stages ADD COLUMN confirmed_by_name VARCHAR(100);

CREATE TABLE notices (
    id UUID PRIMARY KEY,
    stage_id UUID NOT NULL REFERENCES stages (id),
    recruitment_id UUID NOT NULL REFERENCES recruitments (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    group_type VARCHAR(10) NOT NULL CHECK (group_type IN ('PASS', 'FAIL')),
    template_type VARCHAR(20) NOT NULL,
    subject VARCHAR(200) NOT NULL,
    greeting TEXT NOT NULL,
    content TEXT NOT NULL,
    closing TEXT NOT NULL,
    required_text TEXT NOT NULL,
    recipient_count INT NOT NULL,
    status VARCHAR(10) NOT NULL CHECK (status IN ('DRAFT', 'SENT', 'PARTIAL', 'EMPTY')),
    sent_count INT NOT NULL DEFAULT 0,
    failed_count INT NOT NULL DEFAULT 0,
    sent_at TIMESTAMP WITH TIME ZONE,
    sent_by UUID,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT notices_stage_group_key UNIQUE (stage_id, group_type)
);

CREATE TABLE notice_deliveries (
    id UUID PRIMARY KEY,
    notice_id UUID NOT NULL REFERENCES notices (id),
    application_id UUID NOT NULL REFERENCES applications (id),
    email VARCHAR(254) NOT NULL,
    status VARCHAR(10) NOT NULL CHECK (status IN ('SENT', 'FAILED')),
    error VARCHAR(255),
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT notice_deliveries_notice_application_key UNIQUE (notice_id, application_id)
);

CREATE TABLE reports (
    id UUID PRIMARY KEY,
    recruitment_id UUID NOT NULL UNIQUE REFERENCES recruitments (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    content TEXT NOT NULL,
    agent VARCHAR(50) NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
