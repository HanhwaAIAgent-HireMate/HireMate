package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.ComposedReport;
import com.hiremate.ai.application.ReportBundle;
import com.hiremate.job.Job;
import com.hiremate.job.JobQueue;
import com.hiremate.job.application.JobStreams;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class RemoteReportAgentTests {

    @Test
    @DisplayName("묶음을 report/compose 작업으로 대기열에 넣고, 작업 대상에 결과를 저장할 리포트 ID를 적는다")
    void queuesBundleAsComposeJob() {
        List<Job> queued = new ArrayList<>();
        JobQueue jobs = new JobQueue(new JobStreams() {
            @Override
            public void add(Job job) {
                queued.add(job);
            }

            @Override
            public boolean isOpen(String type, String target) {
                return false;
            }
        }, JsonMapper.builder().build());
        UUID reportId = UUID.randomUUID();
        UUID stageId = UUID.randomUUID();
        ReportBundle bundle = new ReportBundle(ReportBundle.Kind.COMPARE, UUID.randomUUID(), UUID.randomUUID(),
                stageId, "결제 플랫폼 백엔드 개발자", Instant.parse("2026-10-29T00:00:00Z"), "협업", false, List.of(),
                List.of(), List.of("A-0001", "A-0002"), null, List.of(), List.of(), List.of(), List.of());

        Optional<ComposedReport> report = new RemoteReportAgent(jobs).compose(reportId, bundle);

        assertThat(report).isEmpty();
        Job job = queued.getFirst();
        assertThat(job.type()).isEqualTo("report/compose");
        assertThat(job.target()).isEqualTo(reportId.toString());
        JsonNode sent = job.payload().get("bundle");
        assertThat(sent.get("kind").asString()).isEqualTo("COMPARE");
        assertThat(sent.get("stageId").asString()).isEqualTo(stageId.toString());
        assertThat(sent.get("targets").size()).isEqualTo(2);
    }
}
