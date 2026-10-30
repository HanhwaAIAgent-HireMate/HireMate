ALTER TABLE interview_questions ADD COLUMN interviewer_role VARCHAR(10)
    CHECK (interviewer_role IN ('HR', 'PRACTICAL'));
