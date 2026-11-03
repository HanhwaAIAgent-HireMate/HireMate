-- 중으로 판정한 인재상. 전체 지원자 거르기에서 인재상을 고르면 상 · 중인 지원자를 남긴다
ALTER TABLE applications ADD COLUMN mid_talents TEXT NOT NULL DEFAULT '';
