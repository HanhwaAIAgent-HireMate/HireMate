-- 접수 확인 메일 양식: 설정 › 안내 메일에서 기업마다 한 번 정하고 모든 공고에 쓴다. 행이 없으면 기본 문장이다.
-- 보낼 때의 양식을 쓰므로, 공고마다 따로 두던 접수 확인 메일(V15)은 지운다.
CREATE TABLE company_receipt_templates (
    company_id UUID PRIMARY KEY REFERENCES companies (id),
    subject VARCHAR(200) NOT NULL,
    body VARCHAR(5000) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

ALTER TABLE job_postings
    DROP COLUMN receipt_subject,
    DROP COLUMN receipt_body;
