package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.ReportInput;
import com.hiremate.job.Job;
import com.hiremate.job.JobQueue;
import com.hiremate.job.application.JobStreams;
import com.hiremate.report.ReportContent;
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
    @DisplayName("input을 report/write 작업으로 대기열에 넣고, 작업 대상에 리포트를 저장할 기업과 채용을 적는다")
    void queuesInputAsWriteJob() {
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
        UUID recruitmentId = UUID.randomUUID();
        UUID applicationId = UUID.randomUUID();
        ReportInput input = new ReportInput(companyId, recruitmentId, "결제 플랫폼 백엔드 개발자", 8,
                List.of(new ReportContent.ReportStage("서류 전형", 8, 4, 4)),
                List.of(new ReportInput.FinalistInput(applicationId, "정유민",
                        List.of(new CandidateAnalysis.Finding("결제 승인 서버 응답 시간을 줄였다", "이력서 > 경력")),
                        List.of("장애 대응 경험을 설명함"))),
                List.of(1L));

        Optional<ReportContent> report = new RemoteReportAgent(jobs).write(companyId, recruitmentId, input);

        assertThat(report).isEmpty();
        Job job = queued.getFirst();
        assertThat(job.type()).isEqualTo("report/write");
        assertThat(job.target()).isEqualTo(companyId + ":" + recruitmentId);
        assertThat(job.payload().size()).isEqualTo(1);
        JsonNode sent = job.payload().get("input");
        assertThat(sent.get("applicantCount").asLong()).isEqualTo(8);
        // ai 서버가 범위 안에서 합격자의 지원자 프로필을 찾도록 기업 · 채용 · 지원서 ID를 보낸다
        assertThat(sent.get("companyId").asString()).isEqualTo(companyId.toString());
        assertThat(sent.get("recruitmentId").asString()).isEqualTo(recruitmentId.toString());
        assertThat(sent.get("finalists").get(0).get("applicationId").asString()).isEqualTo(applicationId.toString());
        assertThat(sent.get("stages").get(0).get("pass").asLong()).isEqualTo(4);
        assertThat(sent.get("finalists").get(0).get("notable").get(0).get("source").asString())
                .isEqualTo("이력서 > 경력");
    }
}
