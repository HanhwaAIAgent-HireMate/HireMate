CREATE TABLE interview_shared_notes (
    stage_id UUID NOT NULL,
    application_id UUID NOT NULL,
    member_id UUID NOT NULL,
    company_id UUID NOT NULL,
    member_name VARCHAR(100) NOT NULL,
    interviewer_role VARCHAR(10) NOT NULL CHECK (interviewer_role IN ('HR', 'PRACTICAL')),
    text TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (stage_id, application_id, member_id),
    FOREIGN KEY (stage_id, application_id) REFERENCES interview_sessions(stage_id, application_id)
);
CREATE INDEX idx_interview_shared_notes_company ON interview_shared_notes(company_id, stage_id, application_id);
