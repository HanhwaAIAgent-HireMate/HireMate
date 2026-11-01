-- 면접관 모드: 면접관은 자기만 보는 Chat 탭을 쓴다. 비어 있으면 같은 기업 HR이 함께 쓰는 탭이다
ALTER TABLE stage_tabs ADD COLUMN owner_member_id UUID REFERENCES members (id);
