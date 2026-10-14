CREATE TABLE interview_questions (
    id UUID PRIMARY KEY,
    stage_id UUID NOT NULL REFERENCES stages (id),
    application_id UUID NOT NULL REFERENCES applications (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    seq INT NOT NULL,
    text VARCHAR(500) NOT NULL,
    source VARCHAR(10) NOT NULL CHECK (source IN ('AI', 'MANUAL')),
    answer TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX interview_questions_application_idx ON interview_questions (application_id, stage_id, seq);

CREATE TABLE interview_schedules (
    stage_id UUID NOT NULL REFERENCES stages (id),
    application_id UUID NOT NULL REFERENCES applications (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    scheduled_at TIMESTAMP WITH TIME ZONE,
    interviewers VARCHAR(200) NOT NULL DEFAULT '',
    PRIMARY KEY (stage_id, application_id)
);
