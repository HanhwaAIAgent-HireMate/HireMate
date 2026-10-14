CREATE TABLE stage_candidates (
    id UUID PRIMARY KEY,
    stage_id UUID NOT NULL REFERENCES stages (id),
    recruitment_id UUID NOT NULL REFERENCES recruitments (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    application_id UUID NOT NULL REFERENCES applications (id),
    decision VARCHAR(10) NOT NULL CHECK (decision IN ('PENDING', 'PASS', 'FAIL')),
    decided_by UUID,
    decided_at TIMESTAMP WITH TIME ZONE,
    final_result VARCHAR(10) CHECK (final_result IN ('PASS', 'FAIL')),
    undecided_at_confirm BOOLEAN NOT NULL DEFAULT FALSE,
    promoted BOOLEAN NOT NULL DEFAULT FALSE,
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    ai_selected BOOLEAN NOT NULL DEFAULT FALSE,
    selected_at TIMESTAMP WITH TIME ZONE,
    score NUMERIC(7, 2),
    memo TEXT NOT NULL DEFAULT '',
    CONSTRAINT stage_candidates_stage_application_key UNIQUE (stage_id, application_id)
);

CREATE INDEX stage_candidates_recruitment_idx ON stage_candidates (recruitment_id);
CREATE INDEX stage_candidates_application_idx ON stage_candidates (application_id);

CREATE TABLE selection_snapshots (
    stage_id UUID PRIMARY KEY REFERENCES stages (id),
    entries TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE activity_logs (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES companies (id),
    actor_id UUID,
    action VARCHAR(50) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id UUID NOT NULL,
    detail TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX activity_logs_company_idx ON activity_logs (company_id, created_at DESC);
