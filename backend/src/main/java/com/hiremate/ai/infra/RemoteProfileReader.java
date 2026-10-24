package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateProfileView;
import com.hiremate.ai.application.ProfileReader;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** ai 서버의 지원자 프로필 조회 (POST /agents/profile/read). {@code HIREMATE_AI_AGENTS_PROFILE=remote}로 켠다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.PROFILE, mode = AiMode.REMOTE)
class RemoteProfileReader implements ProfileReader {

    private final AiServerClient client;

    RemoteProfileReader(AiServerClient client) {
        this.client = client;
    }

    @Override
    public CandidateProfileView read(UUID companyId, UUID recruitmentId, UUID applicationId) {
        return client.post(AiAgent.PROFILE, "read",
                Map.of("companyId", companyId, "recruitmentId", recruitmentId, "applicationId", applicationId),
                CandidateProfileView.class);
    }
}
