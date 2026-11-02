-- 회사 주소. 설정 › 회사 소개에서 적고 채용 페이지 맨 아래에 보여 준다 (게시한 공고에도 늘 지금 주소)
ALTER TABLE companies ADD COLUMN address VARCHAR(200) NOT NULL DEFAULT '';
