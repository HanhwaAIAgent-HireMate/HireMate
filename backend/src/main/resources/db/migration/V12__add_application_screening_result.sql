-- Application Agent의 서류 평가 결과. score_passed는 자격요건 75% 통과 여부로 쓴다
ALTER TABLE applications
    ADD COLUMN score_held BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN qualification_shortfalls TEXT NOT NULL DEFAULT '';
