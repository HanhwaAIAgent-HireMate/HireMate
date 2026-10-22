package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.AssessmentAgent;
import com.hiremate.ai.application.AssessmentInput;
import com.hiremate.job.Job;
import com.hiremate.job.JobQueue;
import com.hiremate.job.application.JobStreams;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class RemoteAssessmentAgentTests {

    @Test
    @DisplayName("input을 assessment/analyze 작업으로 대기열에 넣고, 점수가 없는 영역은 null로 보낸다")
    void queuesInputAsAnalysisJob() {
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
        Map<String, BigDecimal> areas = new LinkedHashMap<>();
        areas.put("의사소통능력", new BigDecimal("80"));
        areas.put("수리능력", null);
        UUID stageId = UUID.randomUUID();
        AssessmentInput input = new AssessmentInput(UUID.randomUUID(), UUID.randomUUID(), stageId, UUID.randomUUID(),
                "직무역량 평가", new BigDecimal("82.5"), areas, "B", null, "https://github.com/example/assignment",
                "코드 구조 설명이 명확했음");

        Optional<AssessmentAgent.AnalyzeResult> result = new RemoteAssessmentAgent(jobs).analyze(input);

        assertThat(result).isEmpty();
        Job job = queued.getFirst();
        assertThat(job.type()).isEqualTo("assessment/analyze");
        assertThat(job.target()).isEqualTo(input.applicationId().toString());
        JsonNode sent = job.payload().get("input");
        assertThat(sent.get("stageId").asString()).isEqualTo(stageId.toString());
        assertThat(sent.get("total").decimalValue()).isEqualByComparingTo("82.5");
        assertThat(sent.get("areas").get("의사소통능력").asInt()).isEqualTo(80);
        assertThat(sent.get("areas").has("수리능력")).isTrue();
        assertThat(sent.get("areas").get("수리능력").isNull()).isTrue();
        assertThat(sent.get("submission").isNull()).isTrue();
        assertThat(sent.get("note").asString()).isEqualTo("코드 구조 설명이 명확했음");
    }
}
