-- 메일 꾸밈의 보조 색을 없앤다. 안내 상자 제목 · 테두리도 대표 색을 쓴다.
ALTER TABLE company_mail_styles DROP COLUMN accent_color;
