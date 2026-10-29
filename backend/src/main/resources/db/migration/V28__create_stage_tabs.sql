-- 전형 화면의 탭: 선택 지원자와 AI Chat 대화방의 묶음. 같은 기업 담당자가 함께 쓴다.
CREATE TABLE stage_tabs (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES companies (id),
    stage_id UUID NOT NULL REFERENCES stages (id),
    number INT NOT NULL,
    name VARCHAR(30) NOT NULL,
    auto_named BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT stage_tabs_stage_number_key UNIQUE (stage_id, number)
);

CREATE TABLE tab_selections (
    tab_id UUID NOT NULL REFERENCES stage_tabs (id) ON DELETE CASCADE,
    application_id UUID NOT NULL REFERENCES applications (id),
    ai BOOLEAN NOT NULL,
    selected_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (tab_id, application_id)
);

-- 이미 시작한 전형마다 탭 1을 만들고 그 전형의 선택 지원자를 옮긴다
INSERT INTO stage_tabs (id, company_id, stage_id, number, name, auto_named, created_at)
SELECT gen_random_uuid(), company_id, stage_id, 1, '탭 1', TRUE, now()
FROM (SELECT DISTINCT company_id, stage_id FROM stage_candidates) started;

INSERT INTO tab_selections (tab_id, application_id, ai, selected_at)
SELECT tab.id, candidate.application_id, candidate.ai_selected, coalesce(candidate.selected_at, now())
FROM stage_candidates candidate
JOIN stage_tabs tab ON tab.stage_id = candidate.stage_id
WHERE candidate.selected;

-- 되돌리기 스냅샷은 탭마다 하나다. 전형 단위로 남아 있던 스냅샷은 옮기지 않는다
DROP TABLE selection_snapshots;

CREATE TABLE selection_snapshots (
    tab_id UUID PRIMARY KEY REFERENCES stage_tabs (id) ON DELETE CASCADE,
    entries TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

ALTER TABLE stage_candidates
    DROP COLUMN selected,
    DROP COLUMN ai_selected,
    DROP COLUMN selected_at;
