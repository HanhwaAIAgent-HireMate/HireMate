CREATE TABLE interview_stage_assignments (
    stage_id UUID PRIMARY KEY REFERENCES stages(id),
    company_id UUID NOT NULL REFERENCES companies(id),
    hr_member_id UUID NOT NULL REFERENCES members(id),
    practical_member_id UUID NOT NULL REFERENCES members(id),
    version BIGINT NOT NULL DEFAULT 0,
    CHECK (hr_member_id <> practical_member_id)
);

-- 같은 전형의 기존 배정이 일치할 때만 공통 설정으로 옮긴다. 서로 다른 배정의 기록은 그대로 남긴다.
INSERT INTO interview_stage_assignments (stage_id, company_id, hr_member_id, practical_member_id)
SELECT stage_id, company_id, MIN(hr_member_id::text)::UUID, MIN(practical_member_id::text)::UUID
FROM interview_sessions
GROUP BY stage_id, company_id
HAVING COUNT(DISTINCT (hr_member_id, practical_member_id)) = 1;

-- 이미 배정한 전형의 다른 지원자도 같은 면접관을 맡긴다. 기존 기록과 메모는 덮어쓰지 않는다.
INSERT INTO interview_sessions (stage_id, application_id, company_id, hr_member_id, practical_member_id)
SELECT candidates.stage_id, candidates.application_id, candidates.company_id,
       assignment.hr_member_id, assignment.practical_member_id
FROM stage_candidates candidates
JOIN interview_stage_assignments assignment
    ON assignment.stage_id = candidates.stage_id AND assignment.company_id = candidates.company_id
ON CONFLICT (stage_id, application_id) DO NOTHING;
