package com.hiremate.apply;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestFixtures.form;
import static com.hiremate.TestFixtures.publish;
import static com.hiremate.TestFixtures.publishBlind;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures.Posting;
import com.hiremate.posting.DocumentType;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class DocumentNormalizationIntegrationTests extends IntegrationTest {
    @Autowired
    private DocumentNormalizationService normalization;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private ApplicationService applications;

    @Test
    void submittedPdfCanBeQueuedAndNormalizedJsonIsPersisted() throws Exception {
        TestApi hr = newHr();
        Posting posting = publish(hr, false);
        String email = "normalize-" + UUID.randomUUID() + "@example.com";
        expect(anonymous().multipart(posting.applyPath(), form(email, false)), 201);
        UUID applicationId = jdbc.queryForObject("select id from applications where email = ?", UUID.class, email);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        normalization.submit(hr.companyId(), recruitmentId, applicationId);
        UUID documentId = jdbc.queryForObject("select id from application_documents where application_id = ?"
                + " and type = 'RESUME'", UUID.class, applicationId);
        UUID jobId = jdbc.queryForObject("select normalization_job_id from application_documents where id = ?",
                UUID.class, documentId);
        assertThat(jobId).isNotNull();
        var result = new NormalizedDocument("1.0", new NormalizedDocument.Metadata(documentId, "resume", null, 1),
                List.of(new NormalizedDocument.Paragraph("block-0001", List.of(1), "정제 결과")));
        normalization.complete(documentId, jobId, result);
        String saved = jdbc.queryForObject("select normalized_document::text from application_documents where id = ?",
                String.class, documentId);
        assertThat(saved).contains("정제 결과", "block-0001");
    }

    @Test
    @DisplayName("지원자 카드는 정제를 마친 서류의 정제 문서를 주고, 블라인드 채용이면 이름을 가린다 (저장본은 그대로)")
    void completedNormalizationIsShownWithTheApplicantNameMasked() throws Exception {
        TestApi hr = newHr();
        Posting posting = publishBlind(hr);
        String email = "normalize-blind-" + UUID.randomUUID() + "@example.com";
        expect(anonymous().multipart(posting.applyPath(), form(email, false)), 201);
        UUID applicationId = jdbc.queryForObject("select id from applications where email = ?", UUID.class, email);
        normalization.submit(hr.companyId(), UUID.fromString(posting.recruitmentId()), applicationId);
        UUID documentId = jdbc.queryForObject("select id from application_documents where application_id = ?"
                + " and type = 'RESUME'", UUID.class, applicationId);
        UUID jobId = jdbc.queryForObject("select normalization_job_id from application_documents where id = ?",
                UUID.class, documentId);
        assertThat(applications.normalizedDocuments(hr.companyId(), applicationId)).isEmpty();

        normalization.complete(documentId, jobId, new NormalizedDocument("1.0",
                new NormalizedDocument.Metadata(documentId, "resume", null, 1),
                List.of(new NormalizedDocument.Paragraph("block-0001", List.of(1), "정유민입니다. 결제 API를 만들었다"))));

        List<NormalizedDocumentView> shown = applications.normalizedDocuments(hr.companyId(), applicationId);
        assertThat(shown).extracting(NormalizedDocumentView::type).containsExactly(DocumentType.RESUME);
        var paragraph = (NormalizedDocument.Paragraph) shown.getFirst().document().blocks().getFirst();
        assertThat(paragraph.text()).doesNotContain("정유민").contains("결제 API를 만들었다");
        assertThat(jdbc.queryForObject("select normalized_document::text from application_documents where id = ?",
                String.class, documentId)).contains("정유민");
    }
}
