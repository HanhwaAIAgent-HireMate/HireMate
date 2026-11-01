ALTER TABLE interview_sessions
    ADD COLUMN hr_memo_version BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN practical_memo_version BIGINT NOT NULL DEFAULT 0;
