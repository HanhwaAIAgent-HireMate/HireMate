package com.hiremate.apply;

import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import com.hiremate.apply.domain.JobApplication;
import com.hiremate.apply.domain.JobApplicationRepository;
import com.hiremate.global.ApiException;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.BlindMask;
import com.hiremate.posting.DocumentType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 지원 문서 정리 요청을 기업과 채용 범위 안에서 구성한다. */
@Service
public class DocumentNormalizationService {
    public static final String NORMALIZE_JOB = "application/normalize";
    public static final String INDEX_JOB = "application/index-document";
    private final JobApplicationRepository applications;
    private final ApplicationDocumentRepository documents;
    private final ApplicationService applicationService;

    private final JobQueue jobs;
    private final ApplicationEventPublisher events;
    private final EntityManager entityManager;

    public DocumentNormalizationService(JobApplicationRepository applications,
            ApplicationDocumentRepository documents, ApplicationService applicationService, JobQueue jobs,
            ApplicationEventPublisher events, EntityManager entityManager) {
        this.applications = applications;
        this.documents = documents;
        this.applicationService = applicationService;
        this.jobs = jobs;
        this.events = events;
        this.entityManager = entityManager;
    }

    @Transactional(readOnly = true)
    public List<DocumentNormalizationRequest> requests(UUID companyId, UUID recruitmentId, UUID applicationId) {
        JobApplication application = applications.findByIdAndCompanyId(applicationId, companyId)
                .filter(candidate -> candidate.getRecruitmentId().equals(recruitmentId))
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "APPLICATION_NOT_FOUND",
                        "Application not found."));
        boolean blind = applicationService.blind(companyId, recruitmentId);
        return documents.findByApplicationId(applicationId).stream()
                .filter(document -> document.getType() != DocumentType.CERTIFICATE)
                .filter(document -> document.getParsedDocument() != null)
                .map(document -> request(application, document, blind))
                .toList();
    }

    /** 문서 잠금이 결과 수신보다 먼저 잡혀 작업 ID와 요청이 함께 커밋된다. */
    @Transactional
    public void enqueue(DocumentNormalizationRequest proposed) {
        ApplicationDocument document = lockedDocument(proposed.documentId()).orElseThrow();
        JobApplication application = applications.findById(document.getApplicationId()).orElseThrow();
        DocumentNormalizationRequest current = request(application, document,
                applicationService.blind(application.getCompanyId(), application.getRecruitmentId()));
        if (!current.equals(proposed)) {
            throw new IllegalArgumentException("Normalization request does not match the current document scope");
        }
        if (document.getNormalizationStatus() != DocumentNormalizationStatus.PENDING) {
            return;
        }
        if (document.getNormalizationJobId() != null && jobs.isOpen(NORMALIZE_JOB, document.getId().toString())) {
            return;
        }
        try {
            UUID jobId = jobs.enqueue(NORMALIZE_JOB, document.getId().toString(), current);
            document.queueNormalization(jobId, current);
        } catch (RuntimeException exception) {
            document.failNormalization();
        }
    }

    @Transactional
    public void complete(UUID documentId, UUID jobId, NormalizedDocument result) {
        Optional<ApplicationDocument> found = lockedDocument(documentId);
        if (found.isEmpty() || !found.get().awaitsNormalization(jobId)) {
            return;
        }
        ApplicationDocument document = found.get();
        DocumentNormalizationRequest expected = document.getNormalizationRequest();
        JobApplication application = applications.findById(document.getApplicationId()).orElseThrow();
        DocumentIndexRequest index;
        try {
            index = new DocumentIndexRequest(expected, result);
            if (!expected.companyId().equals(application.getCompanyId())
                    || !expected.recruitmentId().equals(application.getRecruitmentId())
                    || !expected.applicationId().equals(application.getId())
                    || !expected.documentId().equals(document.getId())
                    || expected.revision() != document.getRevision()
                    || expected.documentType() != document.getType()) {
                throw new IllegalArgumentException("Normalization scope changed");
            }
        } catch (IllegalArgumentException | NullPointerException exception) {
            document.failNormalization();
            return;
        }
        document.completeNormalization(result);
        events.publishEvent(new DocumentNormalized(index));
    }

    @Transactional
    public void fail(UUID documentId, UUID jobId) {
        lockedDocument(documentId).filter(document -> document.awaitsNormalization(jobId))
                .ifPresent(ApplicationDocument::failNormalization);
    }

    /** 새 시도는 새 버전을 사용하며 지난 성공 결과는 지우지 않는다. */
    @Transactional
    public void retry(UUID companyId, UUID recruitmentId, UUID applicationId, UUID documentId) {
        applications.findByIdAndCompanyId(applicationId, companyId)
                .filter(application -> application.getRecruitmentId().equals(recruitmentId))
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "APPLICATION_NOT_FOUND",
                        "Application not found."));
        ApplicationDocument document = lockedDocument(documentId)
                .filter(candidate -> candidate.getApplicationId().equals(applicationId))
                .filter(candidate -> candidate.getType() != DocumentType.CERTIFICATE)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found."));
        reparse(document, companyId, recruitmentId);
    }

    /** 기업의 채용 범위 안에서 기존 문서를 처리한다. 진행 중이거나 성공한 버전은 그대로 둔다. */
    @Transactional
    public void backfill(UUID companyId, UUID recruitmentId) {
        applicationService.blind(companyId, recruitmentId);
        for (JobApplication application : applications.findByRecruitmentIdAndCompanyId(recruitmentId, companyId)) {
            for (ApplicationDocument candidate : documents.findByApplicationId(application.getId())) {
                ApplicationDocument document = lockedDocument(candidate.getId()).orElseThrow();
                if (document.getType() == DocumentType.CERTIFICATE) {
                    continue;
                }
                if (document.getParsedDocument() != null
                        && document.getNormalizationStatus() != DocumentNormalizationStatus.FAILED) {
                    if (document.getNormalizationStatus() == DocumentNormalizationStatus.PENDING) {
                        events.publishEvent(new DocumentNormalizationRequested(application.getId(),
                                recruitmentId, companyId));
                    }
                    continue;
                }
                reparse(document, companyId, recruitmentId);
            }
        }
    }

    private void reparse(ApplicationDocument document, UUID companyId, UUID recruitmentId) {
        document.requestNormalization();
        try {
            ParsedDocument parsed = applicationService.parseOriginal(companyId, document.getFileId(),
                    applicationService.blind(companyId, recruitmentId));
            document.recordParsedDocument(parsed);
            if (parsed.sources().isEmpty()) {
                document.failNormalization();
                return;
            }
        } catch (RuntimeException exception) {
            document.failNormalization();
            return;
        }
        events.publishEvent(new DocumentNormalizationRequested(document.getApplicationId(), recruitmentId, companyId));
    }

    @Transactional(readOnly = true)
    public List<DocumentNormalizationRequest> pending(Instant before) {
        return documents.findPendingNormalization(before).stream().map(document -> {
            JobApplication application = applications.findById(document.getApplicationId()).orElseThrow();
            return request(application, document,
                    applicationService.blind(application.getCompanyId(), application.getRecruitmentId()));
        }).toList();
    }

    /** 저장된 성공 결과로 인덱스 작업을 복구한다. 이후 정리 작업의 상태와 독립적이다. */
    @Transactional(readOnly = true)
    public List<DocumentIndexRequest> indexRequests() {
        return documents.findNormalizedDocuments().stream()
                .map(document -> new DocumentIndexRequest(document.getNormalizedRequest(),
                        document.getNormalizedDocument())).toList();
    }

    /** 저장된 성공 JSON만 큐에 넣고 작업과 버전을 함께 기록한다. */
    @Transactional
    public void enqueueIndex(DocumentIndexRequest proposed) {
        ApplicationDocument document = lockedDocument(proposed.document().documentId()).orElseThrow();
        if (!proposed.document().equals(document.getNormalizedDocument())
                || !proposed.request().equals(document.getNormalizedRequest())) {
            return;
        }
        int revision = proposed.document().revision();
        if (Integer.valueOf(revision).equals(document.getIndexRevision())
                && (document.getIndexStatus() == DocumentNormalizationStatus.COMPLETED
                || document.getIndexStatus() == DocumentNormalizationStatus.PENDING
                && jobs.isOpen(INDEX_JOB, document.getId().toString()))) {
            return;
        }
        try {
            document.queueIndex(jobs.enqueue(INDEX_JOB, document.getId().toString(), proposed), revision);
        } catch (RuntimeException exception) {
            document.failIndex();
        }
    }

    @Transactional
    public void completeIndex(UUID documentId, UUID jobId, DocumentIndexResult result) {
        lockedDocument(documentId).filter(document -> document.awaitsIndex(jobId)).ifPresent(document -> {
            if (result != null && documentId.equals(result.documentId())
                    && result.revision() == document.getIndexRevision()
                    && !"STALE".equals(result.status())) {
                document.completeIndex();
            } else {
                document.failIndex();
            }
        });
    }

    @Transactional
    public void failIndex(UUID documentId, UUID jobId) {
        lockedDocument(documentId).filter(document -> document.awaitsIndex(jobId))
                .ifPresent(ApplicationDocument::failIndex);
    }

    private Optional<ApplicationDocument> lockedDocument(UUID documentId) {
        Optional<ApplicationDocument> document = documents.findLockedById(documentId);
        // 호출자의 트랜잭션이 먼저 읽은 엔티티도 잠금 안에서 최신 상태로 다시 읽는다.
        document.ifPresent(value -> entityManager.refresh(value, LockModeType.PESSIMISTIC_WRITE));
        return document;
    }

    private static DocumentNormalizationRequest request(JobApplication application, ApplicationDocument document,
            boolean blind) {
        List<DocumentSource> sources = document.getParsedDocument().sources().stream()
                .map(source -> new DocumentSource(source.id(), source.page(), blind
                        ? BlindMask.maskApplicant(BlindMask.mask(source.text()), application.getName())
                        : source.text()))
                .toList();
        return new DocumentNormalizationRequest(application.getCompanyId(), application.getRecruitmentId(),
                application.getId(), document.getId(), document.getRevision(), document.getType(), sources);
    }
}
