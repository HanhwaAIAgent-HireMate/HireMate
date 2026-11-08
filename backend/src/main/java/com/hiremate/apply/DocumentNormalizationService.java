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
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 제출 문서를 현재 기업과 채용 범위에서 JSON 정제 작업으로 보낸다. */
@Service
public class DocumentNormalizationService {
    public static final String JOB = "application/normalize";
    private final JobApplicationRepository applications;
    private final ApplicationDocumentRepository documents;
    private final FileService files;
    private final JobQueue jobs;

    public DocumentNormalizationService(JobApplicationRepository applications, ApplicationDocumentRepository documents,
            FileService files, JobQueue jobs) {
        this.applications = applications;
        this.documents = documents;
        this.files = files;
        this.jobs = jobs;
    }

    @Transactional
    public void submit(UUID companyId, UUID recruitmentId, UUID applicationId) {
        JobApplication application = applications.findByIdAndCompanyId(applicationId, companyId)
                .filter(value -> recruitmentId.equals(value.getRecruitmentId())).orElseThrow();
        for (UUID id : documents.findIdsByApplicationId(applicationId)) {
            documents.findLockedById(id).ifPresent(document -> enqueue(application, document));
        }
    }

    @Transactional
    public void recover(Instant before) {
        for (UUID id : documents.findPendingNormalizationIds(before)) {
            documents.findLockedById(id).ifPresent(document -> applications.findById(document.getApplicationId())
                    .ifPresent(application -> enqueue(application, document)));
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
        documents.findLockedById(documentId).ifPresent(document -> document.completeNormalization(jobId, result));
    }

    @Transactional
    public void fail(UUID documentId, UUID jobId) {
        documents.findLockedById(documentId).ifPresent(document -> document.failNormalization(jobId));
    }
}
