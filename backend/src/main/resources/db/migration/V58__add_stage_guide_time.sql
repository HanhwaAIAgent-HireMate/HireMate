-- 면접이 아닌 전형(평가 · 시험)의 안내 시작 시각. 면접은 지원자마다 배정한 시간을 메일에 넣어 비워 둔다.
ALTER TABLE stages
    ADD COLUMN guide_time TIME;
