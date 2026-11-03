-- 블라인드 채용. 켜면 학력 · 출신 학교를 공고와 AI 판단에 쓰지 않는다. 기존 공고는 모두 블라인드가 아니다
ALTER TABLE job_postings ADD COLUMN blind BOOLEAN NOT NULL DEFAULT FALSE;
