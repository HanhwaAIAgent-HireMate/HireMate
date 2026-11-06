package com.hiremate.apply;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import com.hiremate.apply.domain.JobApplication;
import com.hiremate.apply.domain.JobApplicationRepository;
import com.hiremate.file.PdfText;
import com.hiremate.global.ApiException;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.DocumentType;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;

class DocumentNormalizationTests {
    private final JobApplication application = new JobApplication(UUID.randomUUID(), UUID.randomUUID(),
            UUID.randomUUID(), 1, "가상지원자", "test@example.com", "010", "");
    private final ApplicationDocument document = new ApplicationDocument(application.getId(), DocumentType.RESUME,
            UUID.randomUUID(), "resume.pdf", 10, "원문");
    private final ApplicationDocumentRepository documents = mock(ApplicationDocumentRepository.class);
    private final JobApplicationRepository applications = mock(JobApplicationRepository.class);
    private final ApplicationService applicationService = mock(ApplicationService.class);
    private final JobQueue jobs = mock(JobQueue.class);
    private final List<Object> events = new ArrayList<>();
    private final ApplicationEventPublisher publisher = events::add;
    private final DocumentNormalizationService service = new DocumentNormalizationService(applications, documents,
            applicationService, jobs, publisher, mock(jakarta.persistence.EntityManager.class));

    @BeforeEach
    void setUp() {
        document.recordParsedDocument(ParsedDocument.from(new PdfText.Result(1,
                List.of(new PdfText.Page(1, "가상지원자 한빛대학교 경력", List.of())), List.of()), false));
        when(documents.findLockedById(document.getId())).thenReturn(Optional.of(document));
        when(documents.findByApplicationId(application.getId())).thenReturn(List.of(document));
        when(applications.findById(application.getId())).thenReturn(Optional.of(application));
        when(applications.findByIdAndCompanyId(application.getId(), application.getCompanyId()))
                .thenReturn(Optional.of(application));
        when(applicationService.blind(application.getCompanyId(), application.getRecruitmentId())).thenReturn(true);
        when(jobs.enqueue(anyString(), anyString(), any())).thenAnswer(ignored -> UUID.randomUUID());
    }

    @Test
    void acceptsOnlyTheCurrentJobOnceAndEmitsTheSavedRequest() {
        DocumentNormalizationRequest request = request();
        service.enqueue(request);
        UUID job = document.getNormalizationJobId();
        NormalizedDocument result = result(request, "s1");
        service.complete(document.getId(), job, result);
        service.complete(document.getId(), job, result);
        service.fail(document.getId(), job);
        assertThat(document.getNormalizedDocument()).isEqualTo(result);
        assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.COMPLETED);
        assertThat(events).hasSize(1);
        DocumentNormalized saved = (DocumentNormalized) events.getFirst();
        assertThat(saved.index().request()).isEqualTo(request);
        assertThat(saved.index().document()).isEqualTo(result);
        assertThat(request.sources().getFirst().text()).doesNotContain("가상지원자", "한빛대학교");
    }

    @Test
    void retryAndNewRevisionKeepPreviousSuccessAndRejectOldResultsAndFailures() {
        DocumentNormalizationRequest first = request();
        service.enqueue(first);
        UUID oldJob = document.getNormalizationJobId();
        NormalizedDocument previous = result(first, "s1");
        service.complete(document.getId(), oldJob, previous);
        service.retry(application.getCompanyId(), application.getRecruitmentId(), application.getId(),
                document.getId());
        assertThat(document.getRevision()).isEqualTo(2);
        assertThat(document.getNormalizedDocument()).isEqualTo(previous);
        service.enqueue(request());
        UUID nextJob = document.getNormalizationJobId();
        service.complete(document.getId(), oldJob, previous);
        service.fail(document.getId(), oldJob);
        assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.PENDING);
        service.fail(document.getId(), nextJob);
        assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.FAILED);
        assertThat(document.getNormalizedDocument()).isEqualTo(previous);
        service.retry(application.getCompanyId(), application.getRecruitmentId(), application.getId(),
                document.getId());
        service.enqueue(request());
        service.complete(document.getId(), nextJob, result(request(), "s1"));
        assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.PENDING);
        service.complete(document.getId(), document.getNormalizationJobId(), result(request(), "s1"));
        assertThat(document.getNormalizedDocument().revision()).isEqualTo(3);
    }

    @Test
    void rejectsWrongDocumentAndUnknownSourcesWithoutReplacingPriorData() {
        service.enqueue(request());
        UUID job = document.getNormalizationJobId();
        service.complete(UUID.randomUUID(), job, result(request(), "s1"));
        service.complete(document.getId(), UUID.randomUUID(), result(request(), "s1"));
        assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.PENDING);
        service.complete(document.getId(), job, result(request(), "unknown"));
        assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.FAILED);
        assertThat(document.getNormalizedDocument()).isNull();
        assertThat(events).isEmpty();
    }

    @Test
    void rejectsForgedCompanyAndMetadataBeforeQueueing() {
        DocumentNormalizationRequest request = request();
        DocumentNormalizationRequest forged = new DocumentNormalizationRequest(UUID.randomUUID(),
                request.recruitmentId(), request.applicationId(), request.documentId(), request.revision(),
                request.documentType(), request.sources());
        assertThatThrownBy(() -> service.enqueue(forged)).isInstanceOf(IllegalArgumentException.class);
        assertThat(document.getNormalizationJobId()).isNull();
        assertThatThrownBy(() -> service.retry(UUID.randomUUID(), application.getRecruitmentId(),
                application.getId(), document.getId())).isInstanceOf(ApiException.class);
        service.enqueue(request);
        NormalizedDocument wrongType = new NormalizedDocument(1, document.getId(), 1,
                DocumentType.PORTFOLIO, List.of());
        service.complete(document.getId(), document.getNormalizationJobId(), wrongType);
        assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.FAILED);
    }

    @Test
    void queueFailureIsRetryableAndDoesNotClearSources() {
        when(jobs.enqueue(anyString(), anyString(), any())).thenThrow(new IllegalStateException("Redis down"));
        service.enqueue(request());
        assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.FAILED);
        assertThat(document.getParsedDocument().sources()).hasSize(1);
        assertThat(document.getText()).isEqualTo("원문");
    }

    @Test
    void recoversLostJobWithNewIdAndRejectsItsDelayedResult() {
        service.enqueue(request());
        UUID lostJob = document.getNormalizationJobId();
        service.enqueue(request());
        UUID recoveredJob = document.getNormalizationJobId();
        assertThat(recoveredJob).isNotEqualTo(lostJob);
        service.complete(document.getId(), lostJob, result(request(), "s1"));
        assertThat(document.getNormalizedDocument()).isNull();
        service.complete(document.getId(), recoveredJob, result(request(), "s1"));
        assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.COMPLETED);
    }

    @Test
    void doesNotDuplicateAnOpenJob() {
        service.enqueue(request());
        UUID currentJob = document.getNormalizationJobId();
        when(jobs.isOpen(DocumentNormalizationService.NORMALIZE_JOB, document.getId().toString())).thenReturn(true);
        service.enqueue(request());
        assertThat(document.getNormalizationJobId()).isEqualTo(currentJob);
    }

    private DocumentNormalizationRequest request() {
        return service.requests(application.getCompanyId(), application.getRecruitmentId(), application.getId())
                .getFirst();
    }

    private static NormalizedDocument result(DocumentNormalizationRequest request, String source) {
        return new NormalizedDocument(1, request.documentId(), request.revision(), request.documentType(),
                List.of(new NormalizedDocument.Paragraph("b1", List.of(source), "body", "정리된 원문")));
    }
}
