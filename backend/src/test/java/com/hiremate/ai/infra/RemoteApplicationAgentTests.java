package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import tools.jackson.databind.json.JsonMapper;

class RemoteApplicationAgentTests {

    private static final UUID RECRUITMENT = UUID.randomUUID();
    private static final ApplicantDetail APPLICANT = new ApplicantDetail(new ApplicantInfo(UUID.randomUUID(),
            RECRUITMENT, 1, "정유민", "yumin@example.com", null, null, List.of(), AnalysisStatus.PENDING,
            Instant.parse("2026-10-21T00:00:00Z")), "010-0000-0000", null, List.of());
    private static final PostingContent POSTING = new PostingContent("응용 소프트웨어 엔지니어", "백엔드 개발", "정규직",
            "경력 3년 이상", "서울", "", List.of(), List.of("Git 기반 협업 경험"), List.of("외부 시스템 연동 인터페이스를 설계한 경험"),
            List.of());
    private static final ScreeningRubric RUBRIC = new ScreeningRubric(UUID.randomUUID(), RECRUITMENT, "test-1", 1,
            List.of(new ScreeningRubric.Criterion("P-01", ScreeningRubric.Category.PREFERENCE,
                    "외부 시스템 연동 인터페이스를 설계한 경험", true, ScreeningRubric.CriterionType.COMPOSITE,
                    new ScreeningRubric.EvaluationRules("본인이 설계했다", "일부만 설계했다", "설계 기록이 없다"),
                    List.of(), "2001020218_23v6")));

    @Test
    @DisplayName("지원서 · 공고 · 평가 기준을 application/analyze 작업으로 대기열에 넣고 결과를 기다리지 않는다")
    void queuesAnalysisJob() {
        JobQueue jobs = mock(JobQueue.class);

        Optional<ApplicationAnalysis> result = new RemoteApplicationAgent(jobs).analyze(APPLICANT, POSTING, RUBRIC);

        assertThat(result).isEmpty();
        verify(jobs).enqueue("application/analyze", APPLICANT.info().applicationId().toString(),
                Map.of("applicant", APPLICANT, "posting", POSTING, "rubric", RUBRIC));
    }

    @Test
    @DisplayName("ai 서버의 candidate-analyst/analyze로 카드의 AI 분석을 받는다")
    void analyzesCandidateThroughAiServer() {
        CandidateAnalysis answer = new CandidateAnalysis(List.of(), List.of(), List.of(),
                List.of(new CandidateAnalysis.Finding("확인 필요", "이력서")), "test-1", List.of(), List.of(), List.of(),
                "Application Agent", false);
        RecordingClient client = new RecordingClient(answer);

        CandidateAnalysis result = new RemoteCandidateAnalyst(client).analyze(APPLICANT, POSTING, RUBRIC);

        assertThat(result).isEqualTo(answer);
        assertThat(client.agent).isEqualTo(AiAgent.CANDIDATE_ANALYST);
        assertThat(client.body).containsKeys("applicant", "posting", "rubric");
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
