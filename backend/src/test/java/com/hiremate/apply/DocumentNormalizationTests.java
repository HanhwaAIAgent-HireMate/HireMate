package com.hiremate.apply;

import static com.hiremate.TestFixtures.pdf;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
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
import org.junit.jupiter.api.DisplayName;
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

    @Test
    @DisplayName("정제 문서는 화면이 근거 밑줄 자리를 찾는 칸 순서대로 펼치고, 시각 자료 안내는 넣지 않는다")
    void readingTextFollowsTheEvidenceSlotOrder() {
        var document = new NormalizedDocument("1.0",
                new NormalizedDocument.Metadata(UUID.randomUUID(), "resume", "이력서", 2), List.of(
                        new NormalizedDocument.Section("s-1", List.of(1), "경력", List.of(
                                new NormalizedDocument.Paragraph("p-1", List.of(1), "결제 서버를 개발했다."),
                                new NormalizedDocument.Listing("l-1", List.of(1), List.of(
                                        new NormalizedDocument.ListItem("i-1", "주문 API", List.of(1), List.of(
                                                new NormalizedDocument.ListItem("i-2", "재고 차감", List.of(1),
                                                        List.of()))))))),
                        new NormalizedDocument.Table("t-1", List.of(2), "기술", List.of("분야", "기술"),
                                List.of(List.of("백엔드", "Spring Boot"), List.of("DB", "PostgreSQL")), "inferred"),
                        new NormalizedDocument.VisualNotice("v-1", List.of(2), "diagram", "suspected",
                                "구성도는 원본 PDF에서 확인해 주세요.")));

        assertThat(document.readingText()).isEqualTo("""
                이력서
                경력
                결제 서버를 개발했다.
                - 주문 API
                  - 재고 차감
                기술
                분야 | 기술
                백엔드 | Spring Boot
                DB | PostgreSQL""");
    }

    @Test
    @DisplayName("AI가 읽는 본문은 정제를 마치면 정제 문서를 펼친 글이고, 정제 전이거나 실패하면 PDF에서 추출한 글이다")
    void readingTextUsesTheNormalizedDocumentOnlyAfterCompletion() {
        var completed = new ApplicationDocument(UUID.randomUUID(), DocumentType.RESUME, UUID.randomUUID(),
                "resume.pdf", 1, "PDF 글");
        UUID job = UUID.randomUUID();
        completed.queueNormalization(job);
        assertThat(completed.readingText()).isEqualTo("PDF 글");
        completed.completeNormalization(job, paragraph(completed, "정제 글"));
        assertThat(completed.readingText()).isEqualTo("정제 글");

        var failed = new ApplicationDocument(UUID.randomUUID(), DocumentType.RESUME, UUID.randomUUID(),
                "resume.pdf", 1, "PDF 글");
        UUID failedJob = UUID.randomUUID();
        failed.queueNormalization(failedJob);
        failed.failNormalization(failedJob);
        assertThat(failed.readingText()).isEqualTo("PDF 글");
    }

    @Test
    @DisplayName("지원서의 서류가 모두 정제를 마쳐야(완료 또는 실패) 분석하라고 알리고, 자격증은 기다리지 않는다")
    void announcesWhenEveryDocumentIsNormalized() {
        var applications = mock(JobApplicationRepository.class);
        var documents = mock(ApplicationDocumentRepository.class);
        var events = mock(ApplicationEventPublisher.class);
        UUID companyId = UUID.randomUUID();
        UUID recruitmentId = UUID.randomUUID();
        var application = new JobApplication(recruitmentId, companyId, UUID.randomUUID(), 1,
                "Name", "user@example.com", "010", "");
        var resume = new ApplicationDocument(application.getId(), DocumentType.RESUME, UUID.randomUUID(),
                "resume.pdf", 1, "이력서");
        var portfolio = new ApplicationDocument(application.getId(), DocumentType.PORTFOLIO, UUID.randomUUID(),
                "portfolio.pdf", 1, "포트폴리오");
        var certificate = new ApplicationDocument(application.getId(), DocumentType.CERTIFICATE, UUID.randomUUID(),
                "certificate.pdf", 1, "자격증");
        UUID resumeJob = UUID.randomUUID();
        UUID portfolioJob = UUID.randomUUID();
        resume.queueNormalization(resumeJob);
        portfolio.queueNormalization(portfolioJob);
        when(documents.findLockedById(resume.getId())).thenReturn(Optional.of(resume));
        when(documents.findLockedById(portfolio.getId())).thenReturn(Optional.of(portfolio));
        when(documents.findByApplicationId(application.getId())).thenReturn(List.of(resume, portfolio, certificate));
        when(applications.findById(application.getId())).thenReturn(Optional.of(application));
        var service = new DocumentNormalizationService(applications, documents, mock(FileService.class),
                mock(JobQueue.class), mock(ApplicationService.class), events);
        var normalized = new ApplicationDocumentsNormalized(application.getId(), recruitmentId, companyId);

        service.complete(resume.getId(), resumeJob, paragraph(resume, "정제 이력서"));
        verify(events, never()).publishEvent(normalized);
        assertThat(service.normalized(application.getId())).isFalse();

        service.fail(portfolio.getId(), portfolioJob);
        verify(events).publishEvent(normalized);
        assertThat(service.normalized(application.getId())).isTrue();

        // 이미 끝난 작업의 결과가 다시 와도 또 알리지 않는다
        service.fail(portfolio.getId(), portfolioJob);
        verify(events).publishEvent(normalized);
    }

    private static NormalizedDocument paragraph(ApplicationDocument document, String text) {
        return new NormalizedDocument("1.0",
                new NormalizedDocument.Metadata(document.getId(), document.getType().name().toLowerCase(), null, 1),
                List.of(new NormalizedDocument.Paragraph("block-0001", List.of(1), text)));
    }
}
