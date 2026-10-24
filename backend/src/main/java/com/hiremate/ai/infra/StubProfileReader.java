package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateProfileView;
import com.hiremate.ai.application.ProfileReader;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 개발용 프로필 조회. 프로필은 ai 서버에만 있으므로 늘 빈 프로필을 돌려준다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.PROFILE, mode = AiMode.STUB)
class StubProfileReader implements ProfileReader {

    @Override
    public CandidateProfileView read(UUID companyId, UUID recruitmentId, UUID applicationId) {
        return CandidateProfileView.empty(applicationId);
    }
}
