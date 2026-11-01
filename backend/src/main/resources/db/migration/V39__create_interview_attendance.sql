-- 면접관 입장: 면접관이 면접 진행 화면에서 [면접 입장]을 누른 때와 마지막으로 접속이 확인된 때.
-- 배정된 면접관이 모두 입장하고 접속 중이어야 면접을 시작한다. 사람 단위로 저장해 담당별 인원이 늘어도 그대로 쓴다
CREATE TABLE interview_attendance (
    stage_id UUID NOT NULL REFERENCES stages (id),
    application_id UUID NOT NULL REFERENCES applications (id),
    member_id UUID NOT NULL REFERENCES members (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    entered_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (stage_id, application_id, member_id)
);
