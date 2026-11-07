package com.hiremate.apply;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestFixtures.form;
import static com.hiremate.TestFixtures.publishBlind;
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import com.hiremate.posting.DocumentType;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class DocumentReprocessingTests extends IntegrationTest {
    @Autowired
    private ApplicationService applications;

    @Autowired
    private DocumentNormalizationService normalization;

    @Autowired
    private ApplicationDocumentRepository documents;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private com.hiremate.file.FileService files;

    @Test
    void sharedPdfFixturesAcceptAndPersistTheLunaResultsForAllThreeTypes() throws Exception {
        TestApi hr = newHr();
        var posting = publishBlind(hr, "");
        Map<String, Object> submitted = form("quality-fixtures@example.com", true);
        submitted.put("name", "Yuna Noh");
        for (var entry : Map.of("resume", "resume", "coverLetter", "cover_letter", "portfolio", "portfolio")
                .entrySet()) {
            Path pdf = Path.of("..", "ai", "tests", "samples", "document_quality_" + entry.getValue() + ".pdf");
            submitted.put(entry.getKey(), new TestApi.FilePart(entry.getValue() + ".pdf", "application/pdf",
                    Files.readAllBytes(pdf)));
        }
        expect(anonymous().multipart(posting.applyPath(), submitted), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        UUID applicationId = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        ObjectMapper json = new ObjectMapper();
        JsonNode expectedSources = json.readTree(Files.readString(
                Path.of("..", "ai", "tests", "samples", "document_quality_sources.json")));
        JsonNode documentsJson = json.readTree(Files.readString(
                Path.of("..", "ai", "tests", "eval", "document_quality_luna_documents.json")));
        var requests = normalization.requests(hr.companyId(), recruitmentId, applicationId);
        assertThat(requests).hasSize(3);
        for (DocumentNormalizationRequest request : requests) {
            String key = switch (request.documentType()) {
                case RESUME -> "resume";
                case COVER_LETTER -> "cover_letter";
                case PORTFOLIO -> "portfolio";
                default -> throw new AssertionError("Unexpected document type");
            };
            JsonNode sources = json.valueToTree(request.sources());
            assertThat(sources).as(key).isEqualTo(expectedSources.get(key));
            NormalizedDocument fixture = json.treeToValue(documentsJson.get(key), NormalizedDocument.class);
            NormalizedDocument result = new NormalizedDocument(fixture.schemaVersion(), request.documentId(),
                    request.revision(), request.documentType(), fixture.blocks());
            normalization.enqueue(request);
            UUID jobId = documents.findById(request.documentId()).orElseThrow().getNormalizationJobId();
            normalization.complete(request.documentId(), jobId, result);

            assertThat(documents.findById(request.documentId()).orElseThrow().getNormalizedDocument())
                    .as(key).isEqualTo(result);
            assertThat(normalization.indexRequests()).contains(new DocumentIndexRequest(request, result));
        }
    }

    @Test
    void recruitmentBackfillReparsesAllThreeOriginalsAndResumesWithoutDuplicatingVersions() throws Exception {
        Fixture fixture = fixture();
        List<ApplicationDocument> originals = documents.findByApplicationId(fixture.applicationId());
        originals.forEach(document -> jdbc.update("update application_documents set parsed_document = null,"
                + " text = 'legacy truncated prefix' where id = ?", document.getId()));
        expect(fixture.hr().post(fixture.path(), null), 202);
        List<DocumentNormalizationRequest> requests = normalization.requests(fixture.hr().companyId(),
                fixture.recruitmentId(), fixture.applicationId());
        assertThat(requests).hasSize(3);
        assertThat(requests).extracting(DocumentNormalizationRequest::documentType)
                .containsExactlyInAnyOrder(DocumentType.RESUME, DocumentType.COVER_LETTER, DocumentType.PORTFOLIO);
        for (DocumentNormalizationRequest request : requests) {
            assertThat(request.sources()).extracting(DocumentSource::page).contains(1, 2);
            String text = request.sources().stream().map(DocumentSource::text)
                    .collect(java.util.stream.Collectors.joining("\n"));
            assertThat(text).hasSizeGreaterThan(20000).contains("FINAL_PAGE_TAIL", "○○학교", "○○○")
                    .doesNotContain("legacy truncated", "Hanbit", "Yuna", "Noh", "3.9");
        }
        expect(fixture.hr().post(fixture.path(), null), 202);
        for (DocumentNormalizationRequest request : requests) {
            assertThat(documents.findById(request.documentId()).orElseThrow().getRevision())
                    .isEqualTo(request.revision());
            normalization.enqueue(request);
        }
        expect(fixture.hr().post(fixture.path(), null), 202);
        for (DocumentNormalizationRequest request : requests) {
            ApplicationDocument document = documents.findById(request.documentId()).orElseThrow();
            assertThat(document.getRevision()).isEqualTo(request.revision());
            assertThat(document.getNormalizationRequest()).isEqualTo(request);
            normalization.complete(request.documentId(), document.getNormalizationJobId(), result(request));
        }
        expect(fixture.hr().post(fixture.path(), null), 202);
        for (DocumentNormalizationRequest request : requests) {
            assertThat(documents.findById(request.documentId()).orElseThrow().getNormalizedDocument())
                    .isEqualTo(result(request));
            assertThat(documents.findById(request.documentId()).orElseThrow().getRevision())
                    .isEqualTo(request.revision());
        }
    }

    @Test
    void explicitRetryReadsOriginalInsteadOfMissingLegacyParsedTextAndChecksScope() throws Exception {
        Fixture fixture = fixture();
        ApplicationDocument document = documents.findByApplicationId(fixture.applicationId()).getFirst();
        jdbc.update("update application_documents set parsed_document = null, text = 'legacy prefix' where id = ?",
                document.getId());
        String path = "/api/recruitments/" + fixture.recruitmentId() + "/applications/"
                + fixture.applicationId() + "/documents/" + document.getId() + "/normalization";
        expect(newHr().post(path, null), 404);
        expect(fixture.hr().post(path.replace(fixture.recruitmentId().toString(), UUID.randomUUID().toString()),
                null), 404);
        expect(fixture.hr().post(path, null), 202);
        ApplicationDocument reparsed = documents.findById(document.getId()).orElseThrow();
        assertThat(reparsed.getParsedDocument().pageCount()).isEqualTo(2);
        assertThat(reparsed.getParsedDocument().sources()).extracting(DocumentSource::text)
                .anyMatch(text -> text.contains("FINAL_PAGE_TAIL"));
        assertThat(reparsed.getText()).isEqualTo("legacy prefix");
        expect(newHr().post(fixture.path(), null), 404);
        expect(newInterviewer(fixture.hr(), "면접관").post(fixture.path(), null), 403);
    }

    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    void failedOriginalReadKeepsAcceptedJsonAndIndexThenBackfillCanResume(boolean foreignFile) throws Exception {
        Fixture fixture = fixture();
        DocumentNormalizationRequest first = normalization.requests(fixture.hr().companyId(),
                fixture.recruitmentId(), fixture.applicationId()).getFirst();
        normalization.enqueue(first);
        normalization.complete(first.documentId(), documents.findById(first.documentId()).orElseThrow()
                .getNormalizationJobId(), result(first));
        normalization.enqueueIndex(new DocumentIndexRequest(first, result(first)));
        ApplicationDocument accepted = documents.findById(first.documentId()).orElseThrow();
        normalization.completeIndex(first.documentId(), accepted.getIndexJobId(),
                new DocumentIndexResult(first.documentId(), first.revision(), "INDEXED"));
        UUID unreadable = files.store(foreignFile ? newHr().companyId() : fixture.hr().companyId(),
                "broken.pdf", "application/pdf",
                new byte[] {1, 2, 3}).fileId();
        jdbc.update("update application_documents set file_id = ? where id = ?", unreadable, first.documentId());
        String path = "/api/recruitments/" + fixture.recruitmentId() + "/applications/"
                + fixture.applicationId() + "/documents/" + first.documentId() + "/normalization";
        expect(fixture.hr().post(path, null), 202);
        ApplicationDocument failed = documents.findById(first.documentId()).orElseThrow();
        assertThat(failed.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.FAILED);
        assertThat(failed.getNormalizedDocument()).isEqualTo(result(first));
        assertThat(failed.getNormalizedRequest()).isEqualTo(first);
        assertThat(failed.getIndexStatus()).isEqualTo(DocumentNormalizationStatus.COMPLETED);
        assertThat(failed.getIndexRevision()).isEqualTo(first.revision());
        jdbc.update("update application_documents set file_id = ? where id = ?",
                accepted.getFileId(), first.documentId());
        expect(fixture.hr().post(fixture.path(), null), 202);
        ApplicationDocument resumed = documents.findById(first.documentId()).orElseThrow();
        assertThat(resumed.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.PENDING);
        assertThat(resumed.getRevision()).isGreaterThan(failed.getRevision());
        assertThat(resumed.getNormalizedDocument()).isEqualTo(result(first));
    }

    private Fixture fixture() throws Exception {
        TestApi hr = newHr();
        var posting = publishBlind(hr, "");
        Map<String, Object> submitted = form(UUID.randomUUID() + "@example.com", true);
        submitted.put("name", "Yuna Noh");
        for (String key : List.of("resume", "coverLetter", "portfolio")) {
            submitted.put(key, new TestApi.FilePart(key + ".pdf", "application/pdf", originalPdf()));
        }
        expect(anonymous().multipart(posting.applyPath(), submitted), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        UUID applicationId = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        return new Fixture(hr, recruitmentId, applicationId);
    }

    private static NormalizedDocument result(DocumentNormalizationRequest request) {
        return new NormalizedDocument(1, request.documentId(), request.revision(), request.documentType(),
                List.of(new NormalizedDocument.Paragraph("b1", List.of(request.sources().getFirst().id()),
                        "body", request.sources().getFirst().text())));
    }

    private static byte[] originalPdf() throws Exception {
        try (PDDocument document = new PDDocument();
                ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            for (int number = 1; number <= 2; number++) {
                PDPage page = new PDPage();
                document.addPage(page);
                try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                    content.beginText();
                    content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                    content.newLineAtOffset(50, 700);
                    content.showText("Hanbit University GPA: 3.9. Applicant Yuna Noh. "
                            + "Java payment project preserved content. ".repeat(350)
                            + (number == 2 ? "FINAL_PAGE_TAIL" : "FIRST_PAGE_TAIL"));
                    content.endText();
                }
            }
            document.save(out);
            return out.toByteArray();
        }
    }

    private record Fixture(TestApi hr, UUID recruitmentId, UUID applicationId) {
        private String path() {
            return "/api/recruitments/" + recruitmentId + "/documents/normalization";
        }
    }
}
