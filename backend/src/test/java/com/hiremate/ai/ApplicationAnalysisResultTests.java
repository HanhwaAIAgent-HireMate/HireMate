package com.hiremate.ai;

import static com.hiremate.TestApi.expect;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Predicate;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import tools.jackson.databind.json.JsonMapper;

/** AI 워커가 결과 스트림에 넣은 지원서 분석을 backend가 기록하는지 확인한다. 워커 대신 결과를 직접 넣는다. */
class ApplicationAnalysisResultTests extends IntegrationTest {

    @Autowired
    private ApplicationService applications;

    @Autowired
    private StringRedisTemplate redis;

    @Autowired
    private JsonMapper json;

    @Value("${hiremate.jobs.result-stream}")
    private String resultStream;

    @Test
    @DisplayName("워커가 끝낸 분석을 지원서에 기록하고, 실패한 분석은 분석 실패로 둔다")
    void recordsWorkerResults() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false);
        expect(anonymous().multipart(posting.applyPath(), TestFixtures.form("worker@example.com", false)), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        UUID applicationId = await(hr.companyId(), recruitmentId,
                info -> info.analysisStatus() == AnalysisStatus.DONE).applicationId();

        send(applicationId, JobStatus.DONE,
                ApplicationAnalysis.of(7, "한빛카드", new BigDecimal("73.3"), true, false, List.of("Git 근거 없음")));
        ApplicantInfo recorded = await(hr.companyId(), recruitmentId,
                info -> new BigDecimal("73.3").equals(info.documentScore()));
        assertThat(recorded.careerYears()).isEqualTo(7);
        assertThat(recorded.lastCompany()).isEqualTo("한빛카드");
        assertThat(recorded.shortfalls()).containsExactly("Git 근거 없음");

        send(applicationId, JobStatus.FAILED, null);
        await(hr.companyId(), recruitmentId, info -> info.analysisStatus() == AnalysisStatus.FAILED);
    }

    private void send(UUID applicationId, JobStatus status, ApplicationAnalysis analysis) {
        JobResult result = new JobResult(UUID.randomUUID(), "application/analyze", applicationId.toString(), status,
                analysis == null ? null : json.valueToTree(analysis), status == JobStatus.FAILED ? "모델 오류" : null);
        redis.opsForStream().add(StreamRecords.string(Map.of("result", json.writeValueAsString(result)))
                .withStreamKey(resultStream));
    }

    private ApplicantInfo await(UUID companyId, UUID recruitmentId, Predicate<ApplicantInfo> done)
            throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            List<ApplicantInfo> found = applications.applicants(companyId, recruitmentId);
            if (!found.isEmpty() && done.test(found.getFirst())) {
                return found.getFirst();
            }
            Thread.sleep(200);
        }
        throw new AssertionError("The analysis result was not recorded.");
    }
}
