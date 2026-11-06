package com.hiremate.ai.application;

import com.hiremate.apply.ApplicationSubmitted;
import com.hiremate.apply.DocumentNormalizationRequest;
import com.hiremate.apply.DocumentNormalizationRequested;
import com.hiremate.apply.DocumentNormalizationService;
import com.hiremate.apply.DocumentNormalized;
import com.hiremate.job.JobQueue;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 접수, 재시도, 유실 복구를 문서별 정리 작업으로 연결한다. */
@Component
class DocumentNormalizationListener {
    private static final Logger log = LoggerFactory.getLogger(DocumentNormalizationListener.class);
    private final DocumentNormalizationService documents;
    private final DocumentNormalizationAgent agent;
    private final AiSettings settings;
    private final JobQueue jobs;
    private final Duration recoverAfter;

    DocumentNormalizationListener(DocumentNormalizationService documents, DocumentNormalizationAgent agent,
            AiSettings settings, JobQueue jobs, @Value("${hiremate.jobs.recover-after}") Duration recoverAfter) {
        this.documents = documents;
        this.agent = agent;
        this.settings = settings;
        this.jobs = jobs;
        this.recoverAfter = recoverAfter;
    }

    @ApplicationModuleListener
    void on(ApplicationSubmitted event) {
        submit(event.companyId(), event.recruitmentId(), event.applicationId());
    }

    @ApplicationModuleListener
    void on(DocumentNormalizationRequested event) {
        submit(event.companyId(), event.recruitmentId(), event.applicationId());
    }

    @ApplicationModuleListener
    void on(DocumentNormalized event) {
        jobs.enqueue(DocumentNormalizationService.INDEX_JOB, event.index().document().documentId().toString(),
                event.index());
    }

    @Scheduled(fixedDelayString = "${hiremate.jobs.retry-interval}")
    void recover() {
        if (settings.isStub(AiAgent.APPLICATION)) {
            return;
        }
        try {
            for (DocumentNormalizationRequest request : documents.pending(Instant.now().minus(recoverAfter))) {
                agent.normalize(request);
            }
        } catch (RuntimeException exception) {
            log.warn("Document normalization recovery failed: {}", exception.getMessage());
        }
    }

    private void submit(UUID companyId, UUID recruitmentId, UUID applicationId) {
        if (!settings.isStub(AiAgent.APPLICATION)) {
            documents.requests(companyId, recruitmentId, applicationId).forEach(agent::normalize);
        }
    }
}
