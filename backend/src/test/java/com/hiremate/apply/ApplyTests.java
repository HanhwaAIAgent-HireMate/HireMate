package com.hiremate.apply;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static com.hiremate.TestFixtures.form;
import static com.hiremate.TestFixtures.publish;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures.Posting;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

class ApplyTests extends IntegrationTest {

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("지원서를 접수하면 PDF 본문을 추출해 분석하고, 같은 이메일은 다시 지원할 수 없다")
    void submitsApplicationAndAnalyzesIt() throws Exception {
        TestApi hr = newHr();
        Posting posting = publish(hr, false);
        TestApi applicant = anonymous();

        JsonNode submitted = json(expect(applicant.multipart(posting.applyPath(), form("yumin@example.com", true)),
                201));
        assertThat(submitted.path("applicationNo").asInt()).isEqualTo(1);
        expect(applicant.multipart(posting.applyPath(), form("YUMIN@example.com", true)), 409);

        Map<String, Object> missingCoverLetter = form("other@example.com", true);
        missingCoverLetter.remove("coverLetter");
        expect(applicant.multipart(posting.applyPath(), missingCoverLetter), 400);
        Map<String, Object> notPdf = form("third@example.com", true);
        notPdf.put("resume", new TestApi.FilePart("resume.pdf", "application/pdf", new byte[] {1, 2, 3}));
        expect(applicant.multipart(posting.applyPath(), notPdf), 400);

        JsonNode list = json(expect(hr.get("/api/recruitments/" + posting.recruitmentId() + "/applications"), 200));
        assertThat(list.path("total").asLong()).isEqualTo(1);
        assertThat(list.path("items").get(0).path("documents").toString()).contains("RESUME", "COVER_LETTER");
        String applicationId = list.path("items").get(0).path("applicationId").asString();

        ApplicantInfo analyzed = awaitAnalysis(hr.companyId(), posting.recruitmentId());
        assertThat(analyzed.analysisStatus()).isEqualTo(AnalysisStatus.DONE);
        assertThat(analyzed.documentScore()).isNotNull();
        assertThat(applications.detail(hr.companyId(), UUID.fromString(applicationId)).documents().getFirst().text())
                .contains("Java");

        byte[] pdf = hr.getBytes("/api/recruitments/" + posting.recruitmentId() + "/applications/" + applicationId
                + "/documents/RESUME").body();
        assertThat(new String(pdf, 0, 5)).isEqualTo("%PDF-");
        expect(newHr().get("/api/recruitments/" + posting.recruitmentId() + "/applications/" + applicationId
                + "/documents/RESUME"), 404);
    }

    @Test
    @DisplayName("공고에서 필수로 정한 포트폴리오가 없으면 접수하지 않고, 마감한 공고는 받지 않는다")
    void enforcesRequiredPortfolioAndClosedPostings() throws Exception {
        TestApi hr = newHr();
        Posting posting = publish(hr, true);
        TestApi applicant = anonymous();

        expect(applicant.multipart(posting.applyPath(), form("a@example.com", false)), 400);
        expect(applicant.multipart(posting.applyPath(), form("a@example.com", true)), 201);

        expect(hr.post("/api/recruitments/" + posting.recruitmentId() + "/posting/close", null), 200);
        expect(applicant.multipart(posting.applyPath(), form("b@example.com", true)), 409);
    }

    @Test
    @DisplayName("분석에 실패한 지원서만 다시 분석을 요청할 수 있고, 다시 분석하면 결과가 기록된다")
    void retriesOnlyFailedAnalysis() throws Exception {
        TestApi hr = newHr();
        Posting posting = publish(hr, false);
        expect(anonymous().multipart(posting.applyPath(), form("retry@example.com", false)), 201);
        ApplicantInfo analyzed = awaitAnalysis(hr.companyId(), posting.recruitmentId());
        String retry = "/api/recruitments/" + posting.recruitmentId() + "/applications/" + analyzed.applicationId()
                + "/analysis";
        expect(hr.post(retry, null), 409);

        applications.markAnalysisFailed(analyzed.applicationId());
        expect(newHr().post(retry, null), 404);
        expect(hr.post(retry, null), 202);

        assertThat(awaitAnalysis(hr.companyId(), posting.recruitmentId()).analysisStatus())
                .isEqualTo(AnalysisStatus.DONE);
    }

    private ApplicantInfo awaitAnalysis(UUID companyId, String recruitmentId) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            List<ApplicantInfo> found = applications.applicants(companyId, UUID.fromString(recruitmentId));
            if (!found.isEmpty() && found.getFirst().analysisStatus() != AnalysisStatus.PENDING) {
                return found.getFirst();
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Analysis did not finish.");
    }
}
