-- 다음 전형 안내 메일에 실제로 안내한 지원자별 면접 일시. 면접 화면이 발송 뒤 바뀐 일정을 알아보는 데 쓴다.
ALTER TABLE notice_deliveries
    ADD COLUMN interview_at TIMESTAMP WITH TIME ZONE;
