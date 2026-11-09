package com.hiremate.apply;

import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import com.hiremate.apply.domain.JobApplication;
import com.hiremate.apply.domain.JobApplicationRepository;
import com.hiremate.file.FileService;
import com.hiremate.file.PdfText;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.DocumentType;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 제출 문서를 현재 기업과 채용 범위에서 JSON 정제 작업으로 보낸다. */
@Service
public class DocumentNormalizationService {
    public static final String JOB = "application/normalize";
    public static final String INDEX_JOB = "application/index-document";
    private final JobApplicationRepository applications;
    private final ApplicationDocumentRepository documents;
    private final FileService files;
    private final JobQueue jobs;
    private final ApplicationService applicationService;
    private final ApplicationEventPublisher events;

    public DocumentNormalizationService(JobApplicationRepository applications, ApplicationDocumentRepository documents,
            FileService files, JobQueue jobs, ApplicationService applicationService,
            ApplicationEventPublisher events) {
        this.applications = applications;
        this.documents = documents;
        this.files = files;
        this.jobs = jobs;
        this.applicationService = applicationService;
        this.events = events;
    }

    @Transactional
    public void submit(UUID companyId, UUID recruitmentId, UUID applicationId) {
        JobApplication application = applications.findByIdAndCompanyId(applicationId, companyId)
                .filter(value -> recruitmentId.equals(value.getRecruitmentId())).orElseThrow();
        for (UUID id : documents.findIdsByApplicationId(applicationId)) {
            documents.findLockedById(id).ifPresent(document -> enqueue(application, document));
        }
        // 정제할 서류가 없거나 모두 바로 실패했으면(글이 없는 PDF 등) 기다릴 결과가 없다
        announceIfNormalized(applicationId);
    }

    @Transactional
    public void recover(Instant before) {
        for (UUID id : documents.findPendingNormalizationIds(before)) {
            documents.findLockedById(id).ifPresent(document -> applications.findById(document.getApplicationId())
                    .ifPresent(application -> {
                        enqueue(application, document);
                        if (!document.normalizing()) {
                            announceIfNormalized(application.getId());
                        }
                    }));
        }
    }

    /** 지원서의 서류가 모두 정제를 마쳤는가 (완료 또는 실패). 서류 분석은 이때 시작한다. 자격증은 정제하지 않아 보지 않는다. */
    @Transactional(readOnly = true)
    public boolean normalized(UUID applicationId) {
        return documents.findByApplicationId(applicationId).stream().noneMatch(ApplicationDocument::normalizing);
    }

    /**
     * 서류가 모두 정제를 마쳤으면 알린다. 서류 둘의 결과가 동시에 오면 둘 다 상대를 아직 정제 중으로 보아 알리지 못할 수 있는데,
     * 그 지원서는 분석 복구(ApplicationAnalysisListener.recover)가 다시 맡긴다.
     */
    private void announceIfNormalized(UUID applicationId) {
        if (normalized(applicationId)) {
            applications.findById(applicationId).ifPresent(application -> events.publishEvent(
                    new ApplicationDocumentsNormalized(application.getId(), application.getRecruitmentId(),
                            application.getCompanyId())));
        }
    }

    private void enqueue(JobApplication application, ApplicationDocument document) {
        if (document.getType() == DocumentType.CERTIFICATE
                || document.getNormalizationStatus() != DocumentNormalizationStatus.PENDING
                || document.getNormalizationJobId() != null && jobs.isOpen(JOB, document.getId().toString())) {
            return;
        }
        PdfText.Result parsed = PdfText.parse(files.read(application.getCompanyId(), document.getFileId()).bytes());
        if (parsed.pages().stream().noneMatch(page -> !page.text().isBlank())) {
            document.failUnqueuedNormalization();
            return;
        }
        var request = new DocumentNormalizationRequest(application.getCompanyId(), application.getRecruitmentId(),
                application.getId(), document.getId(), 1, document.getType(), parsed.pages());
        try {
            document.queueNormalization(jobs.enqueue(JOB, document.getId().toString(), request));
        } catch (RuntimeException exception) {
            document.failUnqueuedNormalization();
        }
    }

    @Transactional
    public void complete(UUID documentId, UUID jobId, NormalizedDocument result) {
        documents.findLockedById(documentId).ifPresent(document -> {
            if (document.awaitsNormalization(jobId)) {
                document.completeNormalization(jobId, result);
                if (document.getNormalizationStatus() == DocumentNormalizationStatus.COMPLETED) {
                    events.publishEvent(new DocumentNormalized(documentId));
                }
                announceIfNormalized(document.getApplicationId());
            }
        });
    }

    @Transactional
    public void fail(UUID documentId, UUID jobId) {
        documents.findLockedById(documentId).ifPresent(document -> {
            if (document.awaitsNormalization(jobId)) {
                document.failNormalization(jobId);
                announceIfNormalized(document.getApplicationId());
            }
        });
    }

    @Transactional
    public void enqueueIndex(UUID documentId) {
        documents.findLockedById(documentId).ifPresent(document -> {
            if (document.getIndexStatus() != DocumentNormalizationStatus.PENDING
                    || document.getNormalizedDocument() == null
                    || document.getIndexJobId() != null && jobs.isOpen(INDEX_JOB, documentId.toString())) {
                return;
            }
            JobApplication application = applications.findById(document.getApplicationId()).orElseThrow();
            boolean blind = applicationService.blind(application.getCompanyId(), application.getRecruitmentId());
            var request = new DocumentIndexRequest(application.getCompanyId(), application.getRecruitmentId(),
                    application.getId(), document.getRevision(), blind, application.getName(),
                    document.getNormalizedDocument().forSearch(application.getName(), blind));
            document.queueIndex(jobs.enqueue(INDEX_JOB, documentId.toString(), request));
        });
    }

    @Transactional(readOnly = true)
    public java.util.List<UUID> pendingIndexes(Instant before) {
        return documents.findPendingIndexIds(before);
    }

    @Transactional
    public void completeIndex(UUID documentId, UUID jobId, DocumentIndexResult result) {
        documents.findLockedById(documentId).ifPresent(document -> document.finishIndex(jobId,
                result != null && documentId.equals(result.documentId()) && result.revision() == document.getRevision()
                        && "DONE".equals(result.status())));
    }

    @Transactional
    public void failIndex(UUID documentId, UUID jobId) {
        documents.findLockedById(documentId).ifPresent(document -> document.finishIndex(jobId, false));
    }
}
