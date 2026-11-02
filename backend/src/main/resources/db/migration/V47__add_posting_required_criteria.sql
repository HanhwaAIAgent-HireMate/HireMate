-- 서류 필수 조건. HR이 공고 작성 화면에서 '필수'로 표시한 자격 요건 · 우대 사항 줄의 글이다.
-- 지원자에게는 보여 주지 않는다 (채용 페이지 응답에 넣지 않는다)
ALTER TABLE job_postings ADD COLUMN required_qualifications TEXT NOT NULL DEFAULT '[]';
ALTER TABLE job_postings ADD COLUMN required_preferred TEXT NOT NULL DEFAULT '[]';
