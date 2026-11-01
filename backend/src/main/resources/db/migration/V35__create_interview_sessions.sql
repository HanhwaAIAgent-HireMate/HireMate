CREATE TABLE interview_sessions (
    stage_id UUID NOT NULL REFERENCES stages(id),
    application_id UUID NOT NULL REFERENCES applications(id),
    company_id UUID NOT NULL REFERENCES companies(id),
    hr_member_id UUID NOT NULL REFERENCES members(id),
    practical_member_id UUID NOT NULL REFERENCES members(id),
    status VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED', 'IN_PROGRESS', 'ENDED')),
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    hr_memo TEXT NOT NULL DEFAULT '',
    practical_memo TEXT NOT NULL DEFAULT '',
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (stage_id, application_id),
    CHECK (hr_member_id <> practical_member_id)
);
CREATE INDEX interview_sessions_hr_idx ON interview_sessions(company_id, hr_member_id);
CREATE INDEX interview_sessions_practical_idx ON interview_sessions(company_id, practical_member_id);
ALTER TABLE interview_questions ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
