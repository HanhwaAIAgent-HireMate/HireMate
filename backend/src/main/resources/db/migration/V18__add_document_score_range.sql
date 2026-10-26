-- 보류 점수: 확인 필요를 0점으로 넣어 계산한 총점과 자격요건 점수. 보류 지원자의 점수 표시와 정렬에 쓴다.
-- 이미 확정된 점수는 확정 점수와 같다
ALTER TABLE applications
    ADD COLUMN document_score_low NUMERIC(4, 1),
    ADD COLUMN qualification_score_low NUMERIC(4, 1);

UPDATE applications
SET document_score_low = document_score,
    qualification_score_low = qualification_score;
