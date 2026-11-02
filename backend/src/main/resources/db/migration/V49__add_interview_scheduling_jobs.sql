CREATE TABLE interview_scheduling_jobs (
    previous_stage_id UUID PRIMARY KEY REFERENCES stages(id),
    company_id UUID NOT NULL REFERENCES companies(id),
    next_stage_id UUID NOT NULL REFERENCES stages(id),
    status VARCHAR(20) NOT NULL,
    error_code VARCHAR(80)
);
