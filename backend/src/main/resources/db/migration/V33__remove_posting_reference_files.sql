-- 설정 › 채용 공고의 "기존 채용공고" PDF를 없앤다. AI가 읽지 않고 저장만 하던 자료다.
-- 회사 파일 목록에서만 지운다. 저장된 파일(stored_files)은 설정에서 지울 때와 같이 남긴다.
DELETE FROM company_files WHERE category = 'POSTING';

ALTER TABLE company_files DROP CONSTRAINT company_files_category_check;
ALTER TABLE company_files ADD CONSTRAINT company_files_category_check CHECK (category IN ('INTRO'));
