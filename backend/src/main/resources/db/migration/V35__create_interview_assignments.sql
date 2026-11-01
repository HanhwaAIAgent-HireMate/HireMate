-- 면접 전형마다 지정한 면접관 계정. 담당(인사 · 실무)마다 계정을 행으로 저장한다.
-- 담당별 인원 · 담당 종류를 바꾸게 되면(팀 논의 중) 행 구조 그대로 늘린다
CREATE TABLE interview_assignments (
    stage_id UUID NOT NULL REFERENCES stages (id),
    interviewer_role VARCHAR(10) NOT NULL CHECK (interviewer_role IN ('HR', 'PRACTICAL')),
    member_id UUID NOT NULL REFERENCES members (id),
    company_id UUID NOT NULL REFERENCES companies (id),
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (stage_id, interviewer_role, member_id)
);

CREATE INDEX interview_assignments_member_idx ON interview_assignments (member_id);
