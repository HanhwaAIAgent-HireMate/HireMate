-- 회사 소개 · 조직 문화 글에서 AI가 뽑은 인재상 요소와, 뽑을 때 읽은 글. 설정의 인재상과 합쳐 지원자 분석에 쓴다
ALTER TABLE companies ADD COLUMN culture_factors TEXT NOT NULL DEFAULT '[]';
ALTER TABLE companies ADD COLUMN culture_factors_source TEXT NOT NULL DEFAULT '';
