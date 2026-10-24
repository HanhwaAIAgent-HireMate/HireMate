package com.hiremate.ai.application;

import java.util.UUID;

/** ai 서버에 저장된 지원자 프로필을 읽는다. 읽기만 하고 프로필을 바꾸지 않는다. */
public interface ProfileReader {

    /** 기업 · 채용이 다른 프로필이거나 아직 없으면 빈 프로필을 돌려준다. */
    CandidateProfileView read(UUID companyId, UUID recruitmentId, UUID applicationId);
}
