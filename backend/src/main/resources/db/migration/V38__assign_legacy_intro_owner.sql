-- 담당(인사 · 실무) 칸이 생기기 전에 만든 1분 자기소개는 담당이 비어 있다. 자기소개는 인사가 기록하므로(INTRO_OWNER)
-- 인사로 채운다. 비어 있으면 면접을 시작할 수 없고(QUESTION_OWNER_REQUIRED), 화면에서도 자기소개 담당은 바꿀 수 없다
UPDATE interview_questions
SET interviewer_role = 'HR'
WHERE text = '1분 자기소개 부탁드립니다.'
  AND interviewer_role IS NULL;
