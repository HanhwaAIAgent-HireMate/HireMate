package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.CandidateProfileView;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import tools.jackson.databind.json.JsonMapper;

class RemoteProfileReaderTests {

    @Test
    @DisplayName("ai 서버의 profile/read로 기업 · 채용 · 지원서를 보내고 확인 상태가 붙은 프로필을 받는다")
    void readsProfileThroughAiServer() {
        UUID companyId = UUID.randomUUID();
        UUID recruitmentId = UUID.randomUUID();
        UUID applicationId = UUID.randomUUID();
        CandidateProfileView answer = new CandidateProfileView(applicationId, CandidateProfileView.Status.DONE,
                "카드 결제 승인 · 정산 4년", List.of(new CandidateProfileView.ProfileItemView("CHECK", "interview",
                        "정산 배치 개선에서 맡은 역할이 서류와 다름", "설계는 팀장님이 하셨고 저는 테스트를 맡았습니다.",
                        "1차 면접 답변", CandidateProfileView.Verification.CONFLICT, UUID.randomUUID())));
        RecordingClient client = new RecordingClient(answer);

        CandidateProfileView result = new RemoteProfileReader(client).read(companyId, recruitmentId, applicationId);

        assertThat(result).isEqualTo(answer);
        assertThat(client.agent).isEqualTo(AiAgent.PROFILE);
        assertThat(client.method).isEqualTo("read");
        assertThat(client.body).containsEntry("companyId", companyId)
                .containsEntry("recruitmentId", recruitmentId)
                .containsEntry("applicationId", applicationId);
    }

    @Test
    @DisplayName("개발용 조회는 프로필이 없는 빈 결과를 준다")
    void stubReturnsEmptyProfile() {
        UUID applicationId = UUID.randomUUID();

        CandidateProfileView result = new StubProfileReader().read(UUID.randomUUID(), UUID.randomUUID(),
                applicationId);

        assertThat(result).isEqualTo(CandidateProfileView.empty(applicationId));
        assertThat(result.status()).isNull();
        assertThat(result.items()).isEmpty();
    }

    /** ai 서버 대신 받은 요청을 기록하고 정해 둔 응답을 돌려준다. */
    private static final class RecordingClient extends AiServerClient {

        private final Object response;
        private AiAgent agent;
        private String method;
        private Map<Object, Object> body;

        RecordingClient(Object response) {
            super(WebClient.builder(), "http://ai.test", Duration.ofSeconds(1), JsonMapper.builder().build());
            this.response = response;
        }

        @Override
        <T> T post(AiAgent agent, String method, Object body, Class<T> type) {
            this.agent = agent;
            this.method = method;
            this.body = new HashMap<>((Map<?, ?>) body);
            return type.cast(response);
        }
    }
}
