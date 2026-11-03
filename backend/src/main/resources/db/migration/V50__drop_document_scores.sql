-- 서류는 점수를 매기지 않는다. 평가 항목별 판정(criterion_marks)과 필수 조건으로 줄 세운다.
-- 서류 평가 총점 · 영역 점수 · 75% 통과 판단 · 점수 보류를 지운다
ALTER TABLE applications
    DROP COLUMN document_score,
    DROP COLUMN document_score_low,
    DROP COLUMN score_passed,
    DROP COLUMN score_held,
    DROP COLUMN qualification_status,
    DROP COLUMN qualification_rate,
    DROP COLUMN qualification_score,
    DROP COLUMN qualification_score_low,
    DROP COLUMN qualification_max,
    DROP COLUMN preference_score,
    DROP COLUMN preference_max;
