package com.hiremate.ai.application;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.apply.ApplicationSubmitted;
import com.hiremate.apply.DocumentNormalizationService;
import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class DocumentNormalizationListenerTests {
    @Test
    void submissionQueuesDocumentNormalization() {
        var service = mock(DocumentNormalizationService.class);
        var settings = mock(AiSettings.class);
        when(settings.isStub(AiAgent.APPLICATION)).thenReturn(false);
        var listener = new DocumentNormalizationListener(service, settings, Duration.ofMinutes(1),
                JsonMapper.builder().build());
        UUID companyId = UUID.randomUUID();
        UUID recruitmentId = UUID.randomUUID();
        UUID applicationId = UUID.randomUUID();
        listener.on(new ApplicationSubmitted(applicationId, recruitmentId, companyId));
        verify(service).submit(companyId, recruitmentId, applicationId);
    }

    @Test
    void workerResultIsStoredAsNormalizedJson() {
        var service = mock(DocumentNormalizationService.class);
        var mapper = JsonMapper.builder().build();
        var listener = new DocumentNormalizationListener(service, mock(AiSettings.class),
                Duration.ofMinutes(1), mapper);
        UUID documentId = UUID.randomUUID();
        UUID jobId = UUID.randomUUID();
        var json = mapper.valueToTree(Map.of("schemaVersion", "1.0", "document", Map.of(
                "id", documentId.toString(), "type", "resume", "title", "이력서", "pageCount", 1),
                "blocks", List.of(Map.of("id", "block-0001", "type", "paragraph", "pages", List.of(1),
                        "text", "본문"))));
        listener.on(new JobFinished(new JobResult(jobId, DocumentNormalizationService.JOB, documentId.toString(),
                JobStatus.DONE, json, null)));
        verify(service).complete(org.mockito.ArgumentMatchers.eq(documentId), org.mockito.ArgumentMatchers.eq(jobId),
                org.mockito.ArgumentMatchers.any());
    }
}
