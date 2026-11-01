-- 지원자별 평가 항목 판정과 상으로 판정된 인재상. 전체 지원자를 충족 개수로 줄 세우고 필수 조건을 확인하는 데 쓴다
ALTER TABLE applications ADD COLUMN criterion_marks TEXT NOT NULL DEFAULT '';
ALTER TABLE applications ADD COLUMN high_talents TEXT NOT NULL DEFAULT '';

-- 서류 전형의 필수 조건. HR이 바꾸기 전에는 행이 없고 공고 기준의 중요 표시(자격요건)를 쓴다
CREATE TABLE stage_requirements (
    stage_id UUID PRIMARY KEY REFERENCES stages(id),
    company_id UUID NOT NULL REFERENCES companies(id),
    criterion_ids TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
