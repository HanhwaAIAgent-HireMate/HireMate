-- 메일 꾸밈 부품: 보조 색, 머리 모양, 안내 상자 모양, 배너 그림.
-- 기존 행은 지금까지 보내던 모양(얇은 색 줄 머리, 옅은 바탕 안내 상자)을 그대로 쓴다
ALTER TABLE company_mail_styles
    ADD COLUMN accent_color VARCHAR(7),
    ADD COLUMN header VARCHAR(10) NOT NULL DEFAULT 'LINE',
    ADD COLUMN guide_box VARCHAR(10) NOT NULL DEFAULT 'FILL',
    ADD COLUMN banner_file_id UUID;
