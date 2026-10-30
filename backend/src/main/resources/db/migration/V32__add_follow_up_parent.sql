-- 🎤 꼬리질문: 면접관이 고른(또는 직접 쓴) 꼬리질문은 원래 질문에 딸린 하위 질문으로 저장한다 (최대 2단계).
--   원래 질문을 지우면 딸린 꼬리질문도 함께 지운다.
ALTER TABLE interview_questions
    ADD COLUMN parent_question_id UUID REFERENCES interview_questions (id) ON DELETE CASCADE;

-- 💾 자동 저장: 타이핑을 멈추면 답변을 DB에만 저장하고(분석 없음), 면접관이 다른 질문으로 넘어갈 때 분석한다.
--   자동 저장만 되고 아직 분석에 넘기지 않은 답변이 있으면 true.
ALTER TABLE interview_questions
    ADD COLUMN answer_pending_analysis BOOLEAN NOT NULL DEFAULT FALSE;
