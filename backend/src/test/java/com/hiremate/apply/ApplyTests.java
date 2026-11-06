package com.hiremate.apply;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static com.hiremate.TestFixtures.form;
import static com.hiremate.TestFixtures.pdf;
import static com.hiremate.TestFixtures.publish;
import static com.hiremate.TestFixtures.publishBlind;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures.Posting;
import com.hiremate.TestMailConfiguration;
import com.hiremate.posting.DocumentType;
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

    @Autowired
    private TestMailConfiguration.RecordingMailClient mail;

    @Autowired
    private DocumentNormalizationService normalization;

    @Autowired
    private com.hiremate.apply.domain.ApplicationDocumentRepository storedDocuments;

    @Test
    void storesParsedPagesAndReturnsOnlyScopedBlindNormalizationSources() throws Exception {
        TestApi hr = newHr();
        Posting posting = publishBlind(hr, "");
        Map<String, Object> submitted = form("normalize@example.com", false);
        submitted.put("name", "Yuna Noh");
        submitted.put("resume", new TestApi.FilePart("resume.pdf", "application/pdf",
                pdf("Hanbit University GPA: 3.9. Applicant Yuna Noh. Java Spring")));
        expect(anonymous().multipart(posting.applyPath(), submitted), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        UUID applicationId = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        var requests = normalization.requests(hr.companyId(), recruitmentId, applicationId);
        assertThat(requests).hasSize(2);
        var resume = requests.stream().filter(request -> request.documentType() == DocumentType.RESUME)
                .findFirst().orElseThrow();
        assertThat(resume.revision()).isEqualTo(1);
        assertThat(resume.sources().getFirst().text()).contains("○○○", "○○학교", "GPA: ○○", "Java Spring")
                .doesNotContain("Yuna", "Noh", "Hanbit", "3.9");
        var stored = storedDocuments.findById(resume.documentId()).orElseThrow();
        assertThat(stored.getParsedDocument().pages()).hasSize(1);
        assertThat(stored.getText()).contains("Yuna Noh").doesNotContain("Hanbit", "3.9");
        assertThat(stored.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.PENDING);
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> normalization.requests(
                UUID.randomUUID(), recruitmentId, applicationId)).isInstanceOf(com.hiremate.global.ApiException.class);
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> normalization.requests(
                hr.companyId(), UUID.randomUUID(), applicationId)).isInstanceOf(com.hiremate.global.ApiException.class);
    }

    @Test
    @DisplayName("블라인드 채용은 마지막 전형 결과를 확정하기 전까지 이름을 가리고(영문 이력서의 이름도), 이메일 · 연락처는 그대로 준다")
    void hidesIdentityForBlindPostingUntilFinalResult() throws Exception {
        TestApi hr = newHr();
        Posting posting = publishBlind(hr, "");
        Map<String, Object> form = form("blind-name@example.com", false);
        // 이름 칸은 한글이고 이력서는 영문이다
        form.put("name", "노유나");
        form.put("resume", new TestApi.FilePart("resume.pdf", "application/pdf",
                pdf("Yuna Noh. Contact blind-name@example.com or 010-1234-5678. Java Spring payment 5 years")));
        expect(anonymous().multipart(posting.applyPath(), form), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());

        ApplicantInfo info = applications.applicants(hr.companyId(), recruitmentId).getFirst();
        assertThat(info.name()).isEqualTo("1번 지원자");
        assertThat(info.email()).isEqualTo("blind-name@example.com");
        ApplicantDetail detail = applications.detail(hr.companyId(), info.applicationId());
        assertThat(detail.phone()).isEqualTo("010-0000-0000");
        assertThat(detail.documents().getFirst().text())
                .contains("○○○. Contact blind-name@example.com or 010-1234-5678.", "Java Spring")
                .doesNotContain("Yuna", "Noh");
        // 파일 이름에도 지원자 이름이 들어 있곤 해서, 보이는 이름과 내려받는 이름을 바꾼다
        assertThat(detail.documents().getFirst().fileName()).isEqualTo("1번 지원자_이력서.pdf");
        String download = hr.getBytes("/api/recruitments/" + recruitmentId + "/applications/" + info.applicationId()
                + "/documents/RESUME").headers().firstValue("Content-Disposition").orElseThrow();
        assertThat(download).doesNotContain("resume.pdf");
        // 원본에 이름이 있는 서류는 열면 이름이 보인다고 안내한다 (영문으로 쓴 이름도 센다)
        assertThat(applications.originalsWithName(hr.companyId(), info.applicationId()))
                .containsExactly(DocumentType.RESUME);
        // 저장한 본문은 가리기 전 글이라, 실제 이름으로 찾으면 찾지 못한다
        assertThat(applications.searchDocuments(hr.companyId(), recruitmentId, "Java")).hasSize(1);
        assertThat(applications.searchDocuments(hr.companyId(), recruitmentId, "Yuna Noh")).isEmpty();
        assertThat(json(expect(hr.get("/api/recruitments/" + recruitmentId + "/applications"), 200))
                .path("items").get(0).path("name").asString()).isEqualTo("1번 지원자");

        // 접수 확인 메일은 지원자 본인에게 가는 메일이라 실제 이메일로 보낸다
        Instant deadline = Instant.now().plus(Duration.ofSeconds(10));
        while (mail.sent.stream().noneMatch(sent -> sent.startsWith("blind-name@example.com|"))
                && Instant.now().isBefore(deadline)) {
            Thread.sleep(100);
        }
        assertThat(mail.sent).anyMatch(sent -> sent.startsWith("blind-name@example.com|"));

        // 전형을 시작해도 가리고, 마지막 전형 결과를 확정하면 최종 합격자 처리를 위해 이름을 보인다
        JsonNode progress = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        assertThat(progress.path("stages").size()).isEqualTo(1);
        assertThat(applications.applicants(hr.companyId(), recruitmentId).getFirst().name()).isEqualTo("1번 지원자");
        expect(hr.post("/api/stages/" + progress.path("stages").get(0).path("id").asString() + "/confirm", null), 200);
        ApplicantInfo revealed = applications.applicants(hr.companyId(), recruitmentId).getFirst();
        assertThat(revealed.name()).isEqualTo("노유나");
        assertThat(revealed.email()).isEqualTo("blind-name@example.com");
    }

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
        assertThat(applications.detail(hr.companyId(), UUID.fromString(applicationId)).documents().getFirst().text())
                .contains("Java");

        byte[] pdf = hr.getBytes("/api/recruitments/" + posting.recruitmentId() + "/applications/" + applicationId
                + "/documents/RESUME").body();
        assertThat(new String(pdf, 0, 5)).isEqualTo("%PDF-");
        expect(newHr().get("/api/recruitments/" + posting.recruitmentId() + "/applications/" + applicationId
                + "/documents/RESUME"), 404);
    }

    @Test
    @DisplayName("블라인드 채용이면 서류 본문의 학교 이름을 가려 저장하고, 원본 PDF는 그대로 둔다")
    void masksSchoolNamesForBlindPosting() throws Exception {
        TestApi hr = newHr();
        Posting posting = publishBlind(hr);
        Map<String, Object> form = form("blind@example.com", false);
        byte[] resume = pdf("Graduated from Hanbit University. Java Spring payment 5 years");
        form.put("resume", new TestApi.FilePart("resume.pdf", "application/pdf", resume));
        expect(anonymous().multipart(posting.applyPath(), form), 201);

        String applicationId = json(expect(hr.get("/api/recruitments/" + posting.recruitmentId() + "/applications"),
                200)).path("items").get(0).path("applicationId").asString();
        assertThat(applications.detail(hr.companyId(), UUID.fromString(applicationId)).documents().getFirst().text())
                .contains("Graduated from ○○학교", "Java Spring")
                .doesNotContain("Hanbit");
        assertThat(hr.getBytes("/api/recruitments/" + posting.recruitmentId() + "/applications/" + applicationId
                + "/documents/RESUME").body()).isEqualTo(resume);
    }

    @Test
    @DisplayName("블라인드 채용이면 제출 전에 서류에서 찾은 학교 이름을 알려 주고, 블라인드가 아니면 보지 않는다")
    void checksSchoolNamesBeforeSubmitOnlyForBlindPosting() throws Exception {
        TestApi hr = newHr();
        Map<String, Object> files = Map.of(
                "resume", new TestApi.FilePart("resume.pdf", "application/pdf",
                        pdf("Graduated from Hanbit University. Java Spring payment 5 years")),
                "coverLetter", new TestApi.FilePart("cover.pdf", "application/pdf", pdf("Collaboration story")));

        Posting blind = publishBlind(hr);
        JsonNode found = json(expect(anonymous().multipart(blind.applyPath() + "/school-check", files), 200))
                .path("documents");
        assertThat(found.size()).isEqualTo(1);
        assertThat(found.get(0).path("type").asString()).isEqualTo("RESUME");
        assertThat(found.get(0).path("names")).extracting(JsonNode::asString).containsExactly("Hanbit University");

        Posting open = publish(hr, false);
        assertThat(json(expect(anonymous().multipart(open.applyPath() + "/school-check", files), 200))
                .path("documents")).isEmpty();
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
