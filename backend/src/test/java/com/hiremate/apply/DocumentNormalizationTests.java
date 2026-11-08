package com.hiremate.apply;

import static com.hiremate.TestFixtures.pdf;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import com.hiremate.apply.domain.JobApplication;
import com.hiremate.apply.domain.JobApplicationRepository;
import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.DocumentType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

class DocumentNormalizationTests {
    @Test
    void acceptsOnlyTheCurrentJobsMatchingDocument() {
        var document = new ApplicationDocument(UUID.randomUUID(), DocumentType.RESUME, UUID.randomUUID(),
                "resume.pdf", 1, "existing text");
        UUID job = UUID.randomUUID();
        document.queueNormalization(job);
        var result = new NormalizedDocument("1.0",
                new NormalizedDocument.Metadata(document.getId(), "resume", null, 1),
                List.of(new NormalizedDocument.Paragraph("block-0001", List.of(1), "정제 내용")));
        document.completeNormalization(UUID.randomUUID(), result);
        assertThat(document.getNormalizedDocument()).isNull();
        document.completeNormalization(job, result);
        assertThat(document.getNormalizedDocument()).isEqualTo(result);
        assertThat(document.getText()).isEqualTo("existing text");
    }

    @Test
    void queuesPageBasedInputFromOriginalPdfWithoutChangingExistingText() throws Exception {
        var applications = mock(JobApplicationRepository.class);
        var documents = mock(ApplicationDocumentRepository.class);
        var files = mock(FileService.class);
        var jobs = mock(JobQueue.class);
        UUID companyId = UUID.randomUUID();
        UUID recruitmentId = UUID.randomUUID();
        var application = new JobApplication(recruitmentId, companyId, UUID.randomUUID(), 1,
                "Name", "user@example.com", "010", "");
        var document = new ApplicationDocument(application.getId(), DocumentType.RESUME, UUID.randomUUID(),
                "resume.pdf", 1, "masked existing text");
        when(applications.findByIdAndCompanyId(application.getId(), companyId)).thenReturn(Optional.of(application));
        when(documents.findIdsByApplicationId(application.getId())).thenReturn(List.of(document.getId()));
        when(documents.findLockedById(document.getId())).thenReturn(Optional.of(document));
        when(files.read(companyId, document.getFileId())).thenReturn(new FileContent(null, pdf("Original text")));
        when(jobs.enqueue(eq("application/normalize"), eq(document.getId().toString()), any()))
                .thenReturn(UUID.randomUUID());
        var service = new DocumentNormalizationService(applications, documents, files, jobs,
                mock(ApplicationService.class), mock(ApplicationEventPublisher.class));
        service.submit(companyId, recruitmentId, application.getId());
        var payload = ArgumentCaptor.forClass(DocumentNormalizationRequest.class);
        verify(jobs).enqueue(eq("application/normalize"), eq(document.getId().toString()), payload.capture());
        assertThat(payload.getValue().pages().getFirst().text()).contains("Original text");
        assertThat(document.getText()).isEqualTo("masked existing text");
    }

    @Test
    void queuesSavedJsonForIndexingWithExistingBlindMask() {
        var applications = mock(JobApplicationRepository.class);
        var documents = mock(ApplicationDocumentRepository.class);
        var files = mock(FileService.class);
        var jobs = mock(JobQueue.class);
        var applicationService = mock(ApplicationService.class);
        UUID companyId = UUID.randomUUID();
        UUID recruitmentId = UUID.randomUUID();
        var application = new JobApplication(recruitmentId, companyId, UUID.randomUUID(), 1,
                "홍길동", "user@example.com", "010", "");
        var document = new ApplicationDocument(application.getId(), DocumentType.RESUME, UUID.randomUUID(),
                "resume.pdf", 1, "본문");
        UUID job = UUID.randomUUID();
        document.queueNormalization(job);
        var result = new NormalizedDocument("1.0", new NormalizedDocument.Metadata(document.getId(), "resume", null, 1),
                List.of(new NormalizedDocument.Paragraph("block-1", List.of(1), "홍길동 한빛대학교 결제 서버 개발")));
        when(documents.findLockedById(document.getId())).thenReturn(Optional.of(document));
        when(applications.findById(application.getId())).thenReturn(Optional.of(application));
        when(applicationService.blind(companyId, recruitmentId)).thenReturn(true);
        when(jobs.enqueue(eq("application/index-document"), eq(document.getId().toString()), any()))
                .thenReturn(UUID.randomUUID());
        var events = mock(ApplicationEventPublisher.class);
        var service = new DocumentNormalizationService(applications, documents, files, jobs, applicationService,
                events);
        service.complete(document.getId(), job, result);
        verify(events).publishEvent(new DocumentNormalized(document.getId()));
        service.enqueueIndex(document.getId());
        var payload = ArgumentCaptor.forClass(DocumentIndexRequest.class);
        verify(jobs).enqueue(eq("application/index-document"), eq(document.getId().toString()), payload.capture());
        var indexed = (NormalizedDocument.Paragraph) payload.getValue().document().blocks().getFirst();
        assertThat(indexed.text()).doesNotContain("홍길동", "한빛대학교");
        assertThat(((NormalizedDocument.Paragraph) document.getNormalizedDocument().blocks().getFirst()).text())
                .contains("홍길동", "한빛대학교");
    }

}
