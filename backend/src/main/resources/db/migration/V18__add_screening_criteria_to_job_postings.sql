-- 서류 평가 기준: 공고 담당이 입력한 자격요건 · 우대사항 평가 항목(JSON)과 선발 인원, 평가 기준 버전.
-- 비어 있으면 설정(hiremate.dummy.screening-rubric)의 더미를 쓴다
ALTER TABLE job_postings
    ADD COLUMN screening_criteria TEXT,
    ADD COLUMN hire_count INT,
    ADD COLUMN criteria_version VARCHAR(100);
