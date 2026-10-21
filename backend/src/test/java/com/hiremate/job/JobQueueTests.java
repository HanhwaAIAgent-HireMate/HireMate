package com.hiremate.job;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import tools.jackson.databind.json.JsonMapper;

/** 작업 스트림에 넣은 작업과 결과 스트림에서 읽은 결과를 실제 Redis로 확인한다. AI 워커 대신 결과를 직접 넣는다. */
class JobQueueTests extends IntegrationTest {

    @Autowired
    private JobQueue jobs;

    @Autowired
    private StringRedisTemplate redis;

    @Autowired
    private JsonMapper json;

    @Value("${hiremate.jobs.stream}")
    private String stream;

    @Value("${hiremate.jobs.result-stream}")
    private String resultStream;

    @Test
    @DisplayName("작업을 작업 스트림에 JSON으로 넣고, 결과를 받으면 결과 스트림에서 지우고 열린 작업을 닫는다")
    void queuesJobAndClosesItOnResult() throws Exception {
        String target = UUID.randomUUID().toString();

        UUID jobId = jobs.enqueue("echo/run", target, Map.of("value", "지원서"));

        assertThat(jobs.isOpen("echo/run", target)).isTrue();
        Job job = redis.opsForStream().range(stream, Range.unbounded()).stream()
                .map(record -> json.readValue(String.valueOf(record.getValue().get("job")), Job.class))
                .filter(found -> found.jobId().equals(jobId))
                .findFirst()
                .orElseThrow();
        assertThat(job.type()).isEqualTo("echo/run");
        assertThat(job.target()).isEqualTo(target);
        assertThat(job.payload().path("value").asString()).isEqualTo("지원서");

        JobResult result = new JobResult(jobId, "echo/run", target, JobStatus.DONE,
                json.valueToTree(Map.of("echo", "지원서")), null);
        redis.opsForStream().add(StreamRecords.string(Map.of("result", json.writeValueAsString(result)))
                .withStreamKey(resultStream));

        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (jobs.isOpen("echo/run", target) && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
        }
        assertThat(jobs.isOpen("echo/run", target)).isFalse();
        assertThat(redis.opsForStream().range(resultStream, Range.unbounded()))
                .noneMatch(record -> String.valueOf(record.getValue().get("result")).contains(jobId.toString()));
    }
}
