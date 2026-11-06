package com.hiremate.ai.application;

import com.hiremate.apply.DocumentIndexResult;
import com.hiremate.apply.DocumentNormalizationService;
import com.hiremate.apply.NormalizedDocument;
import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/** 워커 결과는 작업 ID와 현재 문서 버전을 검증한 뒤 apply 서비스로만 저장한다. */
@Component
class DocumentNormalizationResults {
    private static final Logger log = LoggerFactory.getLogger(DocumentNormalizationResults.class);
    private final DocumentNormalizationService documents;
    private final JsonMapper json;

    DocumentNormalizationResults(DocumentNormalizationService documents, JsonMapper json) {
        this.documents = documents;
        this.json = json;
    }

    @ApplicationModuleListener
    void on(JobFinished event) {
        JobResult result = event.result();
        boolean index = DocumentNormalizationService.INDEX_JOB.equals(result.type());
        if (!index && !DocumentNormalizationService.NORMALIZE_JOB.equals(result.type())) {
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
                    documents.completeIndex(documentId, result.jobId(),
                            json.treeToValue(result.result(), DocumentIndexResult.class));
                } catch (RuntimeException exception) {
                    documents.failIndex(documentId, result.jobId());
                }
            } else {
                documents.failIndex(documentId, result.jobId());
            }
            return;
        }
        if (result.status() == JobStatus.DONE) {
            NormalizedDocument document;
            try {
                document = json.treeToValue(result.result(), NormalizedDocument.class);
            } catch (RuntimeException exception) {
                log.warn("Document normalization result for {} is invalid", documentId);
                documents.fail(documentId, result.jobId());
                return;
            }
            documents.complete(documentId, result.jobId(), document);
        } else {
            documents.fail(documentId, result.jobId());
        }
    }
}
