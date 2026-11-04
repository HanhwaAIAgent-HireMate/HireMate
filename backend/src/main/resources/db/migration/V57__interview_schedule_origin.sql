-- 구분값이 없던 기존 일정은 보존한다. 새로 자동 배정한 일정만 재배정 대상이다.
ALTER TABLE interview_schedules ADD COLUMN automatically_scheduled boolean NOT NULL DEFAULT false;
ALTER TABLE interview_scheduling_jobs ADD COLUMN reassign_automatic boolean NOT NULL DEFAULT false;
