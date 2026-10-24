-- 서류 평가: 자격요건 50점 + 우대사항 50점, 소수 첫째 자리. 75% 통과 판단과 총점 확정 여부를 따로 남긴다
ALTER TABLE applications ALTER COLUMN document_score TYPE NUMERIC(4, 1);
ALTER TABLE applications
    ADD COLUMN qualification_status VARCHAR(20) NOT NULL DEFAULT 'UNDETERMINED',
    ADD COLUMN qualification_rate NUMERIC(4, 1),
    ADD COLUMN qualification_score NUMERIC(4, 1),
    ADD COLUMN qualification_max INT NOT NULL DEFAULT 0,
    ADD COLUMN preference_score NUMERIC(4, 1),
    ADD COLUMN preference_max INT NOT NULL DEFAULT 0,
    ADD COLUMN criteria_version VARCHAR(100);
