package com.hiremate.ai.application;

import com.hiremate.apply.ApplicationSubmitted;
import com.hiremate.apply.DocumentIndexResult;
import com.hiremate.apply.DocumentNormalizationService;
import com.hiremate.apply.DocumentNormalized;
import com.hiremate.apply.NormalizedDocument;
import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/** 제출 문서의 정제 요청과 워커 결과를 연결한다. */
@Component
class DocumentNormalizationListener {
    private static final Logger log = LoggerFactory.getLogger(DocumentNormalizationListener.class);
    private final DocumentNormalizationService documents;
    private final AiSettings settings;
    private final Duration recoverAfter;
    private final JsonMapper json;

    DocumentNormalizationListener(DocumentNormalizationService documents, AiSettings settings,
            @Value("${hiremate.jobs.recover-after}") Duration recoverAfter, JsonMapper json) {
        this.documents = documents;
        this.settings = settings;
        this.recoverAfter = recoverAfter;
        this.json = json;
    }

    @ApplicationModuleListener
    void on(ApplicationSubmitted event) {
        if (!settings.isStub(AiAgent.APPLICATION)) {
            documents.submit(event.companyId(), event.recruitmentId(), event.applicationId());
        }
    }

    @ApplicationModuleListener
    void on(JobFinished event) {
        JobResult result = event.result();
        boolean index = DocumentNormalizationService.INDEX_JOB.equals(result.type());
        if (!index && !DocumentNormalizationService.JOB.equals(result.type())) {
            return;
        }
        UUID documentId;
        try {
            documentId = UUID.fromString(result.target());
        } catch (IllegalArgumentException | NullPointerException exception) {
            log.warn("Document normalization result has an invalid target");
            return;
        }
        if (index) {
            if (result.status() == JobStatus.DONE) {
                try {
                    documents.completeIndex(documentId, result.jobId(), json.treeToValue(result.result(),
                            DocumentIndexResult.class));
                } catch (RuntimeException exception) {
                    documents.failIndex(documentId, result.jobId());
                }
            } else {
                documents.failIndex(documentId, result.jobId());
            }
            return;
        }
        if (result.status() != JobStatus.DONE) {
            documents.fail(documentId, result.jobId());
            return;
        }
        try {
            NormalizedDocument document = json.treeToValue(result.result(), NormalizedDocument.class);
            documents.complete(documentId, result.jobId(), document);
        } catch (RuntimeException exception) {
            log.warn("Document normalization result for {} is invalid", documentId);
            documents.fail(documentId, result.jobId());
        }
    }

    @ApplicationModuleListener
    void on(DocumentNormalized event) {
        if (!settings.isStub(AiAgent.APPLICATION)) {
            documents.enqueueIndex(event.documentId());
        }
    }

    @Scheduled(fixedDelayString = "${hiremate.jobs.retry-interval}")
    void recover() {
        if (!settings.isStub(AiAgent.APPLICATION)) {
            try {
                documents.recover(Instant.now().minus(recoverAfter));
                documents.pendingIndexes(Instant.now().minus(recoverAfter)).forEach(documents::enqueueIndex);
            } catch (RuntimeException exception) {
                log.warn("Document normalization recovery failed: {}", exception.getMessage());
            }
        }
    }
}
