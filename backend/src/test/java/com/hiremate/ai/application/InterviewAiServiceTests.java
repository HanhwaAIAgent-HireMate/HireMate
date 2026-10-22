package com.hiremate.ai.application;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.hiremate.apply.ApplicationService;
import com.hiremate.company.CompanyService;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.QuestionSource;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.PostingService;
import com.hiremate.screening.ScreeningService;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class InterviewAiServiceTests {

    private final InterviewService interviews = mock(InterviewService.class);
    private final InterviewAgent agent = mock(InterviewAgent.class);
    private final JobQueue jobs = mock(JobQueue.class);
    private final AiSettings settings = mock(AiSettings.class);
    private final InterviewAiService service = new InterviewAiService(interviews, mock(CompanyService.class),
            mock(ApplicationService.class), mock(PostingService.class), mock(ScreeningService.class),
            mock(CandidateAnalyst.class), agent, jobs, settings);
    private final UUID companyId = UUID.randomUUID();
    private final UUID stageId = UUID.randomUUID();
    private final UUID applicationId = UUID.randomUUID();

    @Test
    @DisplayName("결과 확정 때 이미 질문을 준비했으면 다음 전형 시작 때 다시 생성하지 않는다")
    void skipsPreparedQuestions() {
        when(interviews.preparationView(companyId, stageId, applicationId)).thenReturn(
                new InterviewView(applicationId, null,
                        List.of(new InterviewView.Question(UUID.randomUUID(), "담당한 역할은?", QuestionSource.AI, "")),
                        List.of()));

        service.prepare(companyId, stageId, applicationId);

        verifyNoInteractions(agent, jobs);
    }

    @Test
    @DisplayName("결과 확정 때 맡긴 질문을 워커가 생성 중이면 다음 전형 시작 때 중복 작업을 넣지 않는다")
    void skipsOpenQuestionJobs() {
        when(interviews.preparationView(companyId, stageId, applicationId))
                .thenReturn(new InterviewView(applicationId, null, List.of(), List.of()));
        when(settings.isStub(AiAgent.INTERVIEW)).thenReturn(false);
        when(jobs.isOpen(InterviewAgent.QUESTIONS_JOB,
                InterviewAgent.jobTarget(companyId, stageId, applicationId))).thenReturn(true);

        service.prepare(companyId, stageId, applicationId);

        verifyNoInteractions(agent);
    }
}
