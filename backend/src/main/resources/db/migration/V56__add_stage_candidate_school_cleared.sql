-- 블라인드 채용 서류 전형에서 HR이 확인해 해제한 블라인드 위반 의심
ALTER TABLE stage_candidates ADD COLUMN school_cleared BOOLEAN NOT NULL DEFAULT FALSE;
