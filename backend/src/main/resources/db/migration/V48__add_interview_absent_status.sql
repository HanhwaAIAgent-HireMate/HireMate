-- 면접 시간에 오지 않은 지원자를 불참(ABSENT)으로 표시한다
ALTER TABLE interview_sessions DROP CONSTRAINT interview_sessions_status_check;
ALTER TABLE interview_sessions ADD CONSTRAINT interview_sessions_status_check
    CHECK (status IN ('SCHEDULED', 'IN_PROGRESS', 'ENDED', 'ABSENT'));
