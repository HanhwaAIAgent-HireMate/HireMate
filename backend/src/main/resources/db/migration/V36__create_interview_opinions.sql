-- 면접관 의견: 배정된 면접관이 지원자마다 남기는 추천도와 이유. 결정은 HR이 하고, 의견은 AI에 넘기지 않는다
CREATE TABLE interview_opinions (
    stage_id UUID NOT NULL REFERENCES stages (id),
    application_id UUID NOT NULL REFERENCES applications (id),
    member_id UUID NOT NULL REFERENCES members (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    member_name VARCHAR(100) NOT NULL,
    interviewer_role VARCHAR(10) NOT NULL CHECK (interviewer_role IN ('HR', 'PRACTICAL')),
    recommendation VARCHAR(16) NOT NULL CHECK (recommendation IN ('RECOMMEND', 'HOLD', 'NOT_RECOMMEND')),
    comment TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (stage_id, application_id, member_id)
);

CREATE INDEX interview_opinions_stage_idx ON interview_opinions (company_id, stage_id);
