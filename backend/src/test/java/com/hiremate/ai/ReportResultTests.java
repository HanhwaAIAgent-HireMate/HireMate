package com.hiremate.ai;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import com.hiremate.report.ReportContent;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** AI 워커가 결과 스트림에 넣은 최종 리포트를 backend가 저장하는지 확인한다. 워커 대신 결과를 직접 넣는다. */
class ReportResultTests extends IntegrationTest {

    @Autowired
    private StringRedisTemplate redis;

    @Autowired
    private JsonMapper json;

    @Value("${hiremate.jobs.result-stream}")
    private String resultStream;

    @Test
    @DisplayName("워커가 쓴 최종 리포트를 저장해 리포트 화면에서 읽는다")
    void savesWorkerReport() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false);
        String path = "/api/recruitments/" + posting.recruitmentId() + "/report";
        expect(hr.get(path), 404);

        ReportContent content = new ReportContent("결제 · 정산 실무 근거가 분명했어요.", 8, 1,
                List.of(new ReportContent.ReportStage("서류 전형", 8, 4, 4)),
                List.of(new ReportContent.Finalist("정유민", "승인 서버 응답 시간을 줄였어요.", List.of("이력서 > 경력"))),
                List.of());
        JobResult result = new JobResult(UUID.randomUUID(), "report/write",
                hr.companyId() + ":" + posting.recruitmentId(), JobStatus.DONE, json.valueToTree(content), null);
        redis.opsForStream().add(StreamRecords.string(Map.of("result", json.writeValueAsString(result)))
                .withStreamKey(resultStream));

        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        HttpResponse<String> response = hr.get(path);
        while (response.statusCode() != 200 && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
            response = hr.get(path);
        }
        JsonNode report = json(expect(response, 200));
        assertThat(report.path("agent").asString()).isEqualTo("Report Agent");
        assertThat(report.path("content").path("summary").asString()).isEqualTo("결제 · 정산 실무 근거가 분명했어요.");
        assertThat(report.path("content").path("finalists").get(0).path("name").asString()).isEqualTo("정유민");
    }
}
