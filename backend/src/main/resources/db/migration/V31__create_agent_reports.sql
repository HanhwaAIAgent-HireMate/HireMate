-- Report Agent 리포트: 전형 결과(STAGE) · 지원자 비교(COMPARE) · 채용 최종(FINAL).
-- bundle은 Agent에 넘긴 묶음 그대로, result는 Agent 결과(부품 설계서)다. 어떤 데이터로 만들었는지 다시 볼 수 있게 둘 다 남긴다.
CREATE TABLE agent_reports (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES companies (id),
    recruitment_id UUID NOT NULL REFERENCES recruitments (id),
    stage_id UUID NOT NULL REFERENCES stages (id),
    kind VARCHAR(10) NOT NULL,
    status VARCHAR(10) NOT NULL,
    requested_by UUID,
    focus VARCHAR(100) NOT NULL DEFAULT '',
    brief BOOLEAN NOT NULL DEFAULT FALSE,
    bundle TEXT NOT NULL,
    result TEXT,
    error VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX ix_agent_reports_stage ON agent_reports (company_id, stage_id, kind, created_at);
