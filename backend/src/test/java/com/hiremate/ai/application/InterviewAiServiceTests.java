package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.hiremate.apply.ApplicationService;
import com.hiremate.company.CompanyService;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.QuestionSource;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.PostingService;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.Decision;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageCandidateView;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class InterviewAiServiceTests {

    private final InterviewService interviews = mock(InterviewService.class);
    private final InterviewAgent agent = mock(InterviewAgent.class);
    private final JobQueue jobs = mock(JobQueue.class);
    private final AiSettings settings = mock(AiSettings.class);
    private final ScreeningService screening = mock(ScreeningService.class);
    private final InterviewAiService service = new InterviewAiService(interviews, mock(CompanyService.class),
            mock(ApplicationService.class), mock(PostingService.class), screening,
            mock(CandidateAnalyst.class), agent, jobs, settings);
    private final UUID companyId = UUID.randomUUID();
    private final UUID stageId = UUID.randomUUID();
    private final UUID applicationId = UUID.randomUUID();

    @Test
    @DisplayName("면접 메모 조회는 현재·이전 면접만 포함하며 다른 전형 메모를 제외한다")
    void memoScopeIsLimitedToInterviewRecords() {
        when(interviews.view(companyId, stageId, applicationId))
                .thenReturn(new InterviewView(applicationId, null, List.of(), List.of()));
        when(screening.history(companyId, applicationId)).thenReturn(List.of(
                new StageCandidateView(stageId, "1차 면접", StageType.INTERVIEW, Decision.PENDING,
                        null, null, "본인 작업 추가 확인"),
                new StageCandidateView(UUID.randomUUID(), "서류", StageType.DOCUMENT, Decision.PASS,
                        null, null, "다른 전형 메모")));
        assertThat(service.memos(companyId, stageId, applicationId))
                .containsExactly(new InterviewerMemo(stageId, "1차 면접", "본인 작업 추가 확인"));
        assertThatThrownBy(() -> service.generateFromMemo(companyId, stageId, applicationId, "메모 참고",
                new InterviewerMemo(stageId, "1차 면접", "존재하지 않는 메모")))
                .isInstanceOf(com.hiremate.global.ApiException.class);
        verifyNoInteractions(agent);
    }

    @Test
    @DisplayName("결과 확정 때 이미 질문을 준비했으면 다음 전형 시작 때 다시 생성하지 않는다")
    void skipsPreparedQuestions() {
        when(interviews.preparationView(companyId, stageId, applicationId)).thenReturn(
                new InterviewView(applicationId, null,
                        List.of(new InterviewView.Question(UUID.randomUUID(), "담당한 역할은?", QuestionSource.AI, "")),
                        List.of()));

        service.prepare(companyId, stageId, applicationId);

        verifyNoInteractions(agent, jobs);
        verify(interviews).finishPreparing(companyId, stageId, applicationId);
    }

    @Test
    @DisplayName("대기열에 넣기 전 자료 준비 중인 첫 지원자도 로딩으로 표시한다")
    void preparingIncludesInputPreparation() {
        when(interviews.preparing(companyId, stageId, applicationId)).thenReturn(true);
        assertThat(service.preparing(companyId, stageId, applicationId)).isTrue();
        verifyNoInteractions(jobs);
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
