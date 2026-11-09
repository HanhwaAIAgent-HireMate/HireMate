package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationAnalysisRequested;
import com.hiremate.apply.ApplicationDocumentsNormalized;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.ApplicationSubmitted;
import com.hiremate.apply.DocumentNormalizationService;
import com.hiremate.job.Job;
import com.hiremate.job.JobQueue;
import com.hiremate.job.application.JobStreams;
import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingService;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 서류 분석을 언제 맡기는지 본다: 정제를 하면 서류 정제가 모두 끝난 뒤, stub이면 접수 즉시. 입력만 기록하는 가짜 Agent를 쓴다. */
class ApplicationAnalysisListenerTests {

    private static final UUID COMPANY = UUID.randomUUID();
    private static final UUID RECRUITMENT = UUID.randomUUID();
    private static final UUID APPLICATION = UUID.randomUUID();

    private final List<ApplicantDetail> analyzed = new ArrayList<>();
    private final ApplicationService applications = mock(ApplicationService.class);
    private final DocumentNormalizationService normalization = mock(DocumentNormalizationService.class);
    private final AiSettings settings = mock(AiSettings.class);
    private boolean open;
    private ApplicationAnalysisListener listener;

    @BeforeEach
    void setUp() {
        PostingService postings = mock(PostingService.class);
        when(postings.draftContext(any(), any())).thenReturn(mock(PostingDraftContext.class));
        when(applications.detailForAnalysis(any())).thenAnswer(call -> mock(ApplicantDetail.class));
        ApplicationAgent agent = (applicant, posting, rubric) -> {
            analyzed.add(applicant);
            return Optional.empty();
        };
        JobQueue jobs = new JobQueue(new JobStreams() {
            @Override
            public void add(Job job) {
            }

            @Override
            public boolean isOpen(String type, String target) {
                return open;
            }
        }, JsonMapper.builder().build());
        listener = new ApplicationAnalysisListener(applications, normalization, postings, agent, jobs, settings,
                Duration.ofMinutes(1));
    }

    @Test
    @DisplayName("정제를 하면 접수 즉시 분석하지 않고, 서류 정제가 모두 끝나면 분석한다")
    void analyzesAfterDocumentsAreNormalized() {
        listener.on(new ApplicationSubmitted(APPLICATION, RECRUITMENT, COMPANY));
        assertThat(analyzed).isEmpty();

        listener.on(new ApplicationDocumentsNormalized(APPLICATION, RECRUITMENT, COMPANY));
        assertThat(analyzed).hasSize(1);
    }

    @Test
    @DisplayName("분석 작업이 이미 대기열에 있으면 정제가 끝났다는 알림을 다시 받아도 또 맡기지 않는다")
    void doesNotQueueTwice() {
        open = true;
        listener.on(new ApplicationDocumentsNormalized(APPLICATION, RECRUITMENT, COMPANY));
        assertThat(analyzed).isEmpty();
    }

    @Test
    @DisplayName("stub은 정제하지 않아 접수 즉시 분석한다")
    void stubAnalyzesOnSubmission() {
        when(settings.isStub(AiAgent.APPLICATION)).thenReturn(true);
        listener.on(new ApplicationSubmitted(APPLICATION, RECRUITMENT, COMPANY));
        listener.on(new ApplicationDocumentsNormalized(APPLICATION, RECRUITMENT, COMPANY));
        assertThat(analyzed).hasSize(1);
    }

    @Test
    @DisplayName("담당자가 다시 분석을 요청하면 정제 상태와 상관없이 바로 분석한다")
    void retriesImmediately() {
        listener.on(new ApplicationAnalysisRequested(APPLICATION, RECRUITMENT, COMPANY));
        assertThat(analyzed).hasSize(1);
    }

    @Test
    @DisplayName("작업을 잃은 지원서를 다시 맡길 때 서류 정제가 아직 끝나지 않은 지원서는 정제를 기다린다")
    void recoverWaitsForNormalization() {
        UUID normalizing = UUID.randomUUID();
        when(applications.pendingAnalyses(any(Instant.class))).thenReturn(List.of(
                new ApplicationAnalysisRequested(normalizing, RECRUITMENT, COMPANY),
                new ApplicationAnalysisRequested(APPLICATION, RECRUITMENT, COMPANY)));
        when(normalization.normalized(normalizing)).thenReturn(false);
        when(normalization.normalized(APPLICATION)).thenReturn(true);

        listener.recover();

        assertThat(analyzed).hasSize(1);
        verify(applications).detailForAnalysis(APPLICATION);
        verify(applications, never()).detailForAnalysis(normalizing);
    }
}
