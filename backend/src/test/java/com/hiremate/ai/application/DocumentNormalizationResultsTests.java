package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import com.hiremate.apply.DocumentNormalizationService;
import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class DocumentNormalizationResultsTests {
    @Test
    void dropsNullTargetWithoutMutatingAnyDocument() {
        DocumentNormalizationService documents = mock(DocumentNormalizationService.class);
        DocumentNormalizationResults consumer = new DocumentNormalizationResults(documents,
                JsonMapper.builder().build());
        JobResult result = new JobResult(UUID.randomUUID(), DocumentNormalizationService.NORMALIZE_JOB,
                null, JobStatus.DONE, null, null);
        assertThatCode(() -> consumer.on(new JobFinished(result))).doesNotThrowAnyException();
        verifyNoInteractions(documents);
    }
}
