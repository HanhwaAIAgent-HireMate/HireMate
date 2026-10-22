package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.InterviewAnalysisInput;
import com.hiremate.ai.application.InterviewAnalyst;
import com.hiremate.job.Job;
import com.hiremate.job.JobQueue;
import com.hiremate.job.application.JobStreams;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class RemoteInterviewAnalystTests {

    @Test
    @DisplayName("면접 기록을 interview-analyst/analyze 작업으로 대기열에 넣고, 작업 대상에 기업 · 전형 · 지원서를 적는다")
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
        UUID companyId = UUID.randomUUID();
        UUID stageId = UUID.randomUUID();
        UUID applicationId = UUID.randomUUID();
        InterviewAnalysisInput input = new InterviewAnalysisInput(companyId, UUID.randomUUID(), stageId, applicationId,
                "2차 면접", List.of(new InterviewAnalysisInput.AnsweredQuestion("가장 어려웠던 장애 대응은?",
                        "정산 배치가 멈췄을 때 재처리 스크립트로 당일 복구했습니다.")),
                List.of(new InterviewAnalysisInput.PreviousInterview("1차 면접", List.of())));

        Optional<InterviewAnalyst.AnalyzeResult> result = new RemoteInterviewAnalyst(jobs).analyze(input);

        assertThat(result).isEmpty();
        Job job = queued.getFirst();
        assertThat(job.type()).isEqualTo("interview-analyst/analyze");
        assertThat(job.target()).isEqualTo(companyId + ":" + stageId + ":" + applicationId);
        JsonNode sent = job.payload().get("input");
        assertThat(sent.get("stageName").asString()).isEqualTo("2차 면접");
        assertThat(sent.get("questions").get(0).get("answer").asString()).startsWith("정산 배치가 멈췄을 때");
        assertThat(sent.get("previous").get(0).get("stageName").asString()).isEqualTo("1차 면접");
    }
}
