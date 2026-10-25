-- 메일 꾸밈: 기업이 고른 메일 색과 로고. 모든 안내 메일과 접수 확인 메일에 쓴다.
-- 행이 없거나 칸이 비어 있으면 기본 색(남색)과 회사 이름 글자를 쓴다
CREATE TABLE company_mail_styles (
    company_id UUID PRIMARY KEY REFERENCES companies (id),
    color VARCHAR(7),
    logo_file_id UUID,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
