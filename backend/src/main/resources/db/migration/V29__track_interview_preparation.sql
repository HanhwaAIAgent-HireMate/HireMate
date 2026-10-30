CREATE TABLE interview_preparations (
    stage_id UUID NOT NULL REFERENCES stages(id),
    application_id UUID NOT NULL REFERENCES applications(id),
    company_id UUID NOT NULL REFERENCES companies(id),
    PRIMARY KEY (stage_id, application_id)
);
