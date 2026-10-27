-- 전형 안내의 일정을 날짜로, 진행 방식을 온라인 · 오프라인으로 바꾼다.
-- 날짜나 진행 방식으로 읽을 수 없는 예전 글은 잃지 않게 기타 안내 앞에 옮긴다.
UPDATE stages
SET guide_note = LEFT(TRIM(BOTH E'\n' FROM
        CASE WHEN guide_schedule <> '' AND guide_schedule !~ '^\d{4}-\d{2}-\d{2}$'
             THEN '일정: ' || guide_schedule || E'\n' ELSE '' END
     || CASE WHEN guide_method <> '' AND guide_method NOT IN ('온라인', '비대면', '화상', '오프라인', '대면')
             THEN '진행 방식: ' || guide_method || E'\n' ELSE '' END
     || guide_note), 1000);

ALTER TABLE stages
    ALTER COLUMN guide_schedule DROP DEFAULT,
    ALTER COLUMN guide_schedule DROP NOT NULL,
    ALTER COLUMN guide_schedule TYPE DATE
        USING CASE WHEN guide_schedule ~ '^\d{4}-\d{2}-\d{2}$' THEN guide_schedule::date END,
    ALTER COLUMN guide_method DROP DEFAULT,
    ALTER COLUMN guide_method DROP NOT NULL,
    ALTER COLUMN guide_method TYPE VARCHAR(20)
        USING CASE WHEN guide_method IN ('온라인', '비대면', '화상') THEN 'ONLINE'
                   WHEN guide_method IN ('오프라인', '대면') THEN 'OFFLINE' END;
