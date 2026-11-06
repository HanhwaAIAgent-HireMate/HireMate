package com.hiremate.ai.application;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestFixtures.form;
import static com.hiremate.TestFixtures.publishBlind;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.DocumentIndexRequest;
import com.hiremate.apply.DocumentIndexResult;
import com.hiremate.apply.DocumentNormalizationRequest;
import com.hiremate.apply.DocumentNormalizationService;
import com.hiremate.apply.DocumentNormalizationStatus;
import com.hiremate.apply.NormalizedDocument;
import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class DocumentNormalizationResultsTests extends IntegrationTest {
    @Autowired
    private ApplicationService applications;

    @Autowired
    private DocumentNormalizationService normalization;

    @Autowired
    private ApplicationDocumentRepository documents;

    @Autowired
    private JsonMapper json;

    @Test
    void malformedAndUnrelatedResultsCannotChangeAnotherAttempt() throws Exception {
        DocumentNormalizationRequest request = fixture();
        normalization.enqueue(request);
        UUID jobId = document(request).getNormalizationJobId();
        DocumentNormalizationResults results = new DocumentNormalizationResults(normalization, json);
        JsonNode invalid = json.readTree("{\"unexpected\":true}");
        results.on(new JobFinished(new JobResult(jobId, DocumentNormalizationService.NORMALIZE_JOB,
                "invalid-target", JobStatus.DONE, invalid, null)));
        results.on(new JobFinished(new JobResult(jobId, "application/analyze", request.documentId().toString(),
                JobStatus.FAILED, null, "failure")));
        results.on(event(request, UUID.randomUUID(), DocumentNormalizationService.NORMALIZE_JOB, invalid));
        assertThat(document(request).getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.PENDING);
        results.on(event(request, jobId, DocumentNormalizationService.NORMALIZE_JOB, invalid));
        assertThat(document(request).getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.FAILED);
        assertThat(document(request).getNormalizedDocument()).isNull();
    }

    @Test
    void malformedCurrentIndexAcknowledgementAndDelayedNormalizeResultsKeepAcceptedJson() throws Exception {
        DocumentNormalizationRequest request = fixture();
        normalization.enqueue(request);
        UUID oldJob = document(request).getNormalizationJobId();
        NormalizedDocument accepted = new NormalizedDocument(1, request.documentId(), request.revision(),
                request.documentType(), List.of(new NormalizedDocument.Paragraph("b1",
                        List.of(request.sources().getFirst().id()), "body", request.sources().getFirst().text())));
        DocumentNormalizationResults results = new DocumentNormalizationResults(normalization, json);
        results.on(event(request, oldJob, DocumentNormalizationService.NORMALIZE_JOB, json.valueToTree(accepted)));
        normalization.enqueueIndex(new DocumentIndexRequest(request, accepted));
        UUID indexJob = document(request).getIndexJobId();
        results.on(event(request, indexJob, DocumentNormalizationService.INDEX_JOB,
                json.readTree("{\"status\":\"INVALID\"}")));
        assertThat(document(request).getIndexStatus()).isEqualTo(DocumentNormalizationStatus.FAILED);
        assertThat(document(request).getNormalizedDocument()).isEqualTo(accepted);
        normalization.enqueueIndex(new DocumentIndexRequest(request, accepted));
        UUID nextIndexJob = document(request).getIndexJobId();
        results.on(event(request, indexJob, DocumentNormalizationService.INDEX_JOB,
                json.valueToTree(new DocumentIndexResult(request.documentId(), request.revision(), "INDEXED"))));
        assertThat(document(request).getIndexStatus()).isEqualTo(DocumentNormalizationStatus.PENDING);
        results.on(event(request, nextIndexJob, DocumentNormalizationService.INDEX_JOB,
                json.valueToTree(new DocumentIndexResult(request.documentId(), request.revision(), "STALE"))));
        assertThat(document(request).getIndexStatus()).isEqualTo(DocumentNormalizationStatus.FAILED);
        normalization.retry(request.companyId(), request.recruitmentId(), request.applicationId(),
                request.documentId());
        results.on(event(request, oldJob, DocumentNormalizationService.NORMALIZE_JOB, json.valueToTree(accepted)));
        assertThat(document(request).getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.PENDING);
        assertThat(document(request).getNormalizedDocument()).isEqualTo(accepted);
        assertThat(document(request).getNormalizedRequest()).isEqualTo(request);
    }

    private DocumentNormalizationRequest fixture() throws Exception {
        var hr = newHr();
        var posting = publishBlind(hr, "");
        expect(anonymous().multipart(posting.applyPath(), form(UUID.randomUUID() + "@example.com", false)), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        UUID applicationId = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        return normalization.requests(hr.companyId(), recruitmentId, applicationId).getFirst();
    }

    private ApplicationDocument document(DocumentNormalizationRequest request) {
        return documents.findById(request.documentId()).orElseThrow();
    }

    private static JobFinished event(DocumentNormalizationRequest request, UUID jobId, String type, JsonNode body) {
        return new JobFinished(new JobResult(jobId, type, request.documentId().toString(), JobStatus.DONE, body, null));
    }
}
