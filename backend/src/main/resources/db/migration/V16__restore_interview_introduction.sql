-- 이미 질문을 준비한 면접도 공통 자기소개를 첫 질문으로 둔다. 기존 질문과 답변은 그대로 보존한다.
INSERT INTO interview_questions (id, stage_id, application_id, company_id, seq, text, source, answer, updated_at)
SELECT gen_random_uuid(), q.stage_id, q.application_id, q.company_id, 0,
       '1분 자기소개 부탁드립니다.', 'AI', '', CURRENT_TIMESTAMP
FROM interview_questions q
GROUP BY q.stage_id, q.application_id, q.company_id
HAVING NOT bool_or(q.text LIKE '%1분%자기소개%');
