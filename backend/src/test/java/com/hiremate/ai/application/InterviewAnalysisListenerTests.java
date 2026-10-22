package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.hiremate.interview.InterviewAnswersChanged;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.QuestionSource;
import com.hiremate.job.Job;
import com.hiremate.job.JobFinished;
import com.hiremate.job.JobQueue;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import com.hiremate.job.application.JobStreams;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 면접 답변이 연달아 바뀔 때 분석 작업을 몇 번 넣는지 본다. ai 서버 대신 넣은 입력만 기록하는 가짜 Agent를 쓴다. */
class InterviewAnalysisListenerTests {

    private static final UUID COMPANY = UUID.randomUUID();
    private static final UUID STAGE = UUID.randomUUID();
    private static final UUID APPLICATION = UUID.randomUUID();
    private static final InterviewAnswersChanged CHANGED = new InterviewAnswersChanged(COMPANY, STAGE, APPLICATION);

    private final List<InterviewAnalysisInput> analyzed = new ArrayList<>();
    private boolean open;
    private String answer = "첫 답변";
    private InterviewAnalysisListener listener;

    @BeforeEach
    void setUp() {
        UUID recruitmentId = UUID.randomUUID();
        RecruitService recruits = mock(RecruitService.class);
        when(recruits.getByStage(COMPANY, STAGE)).thenReturn(new RecruitmentInfo(recruitmentId, COMPANY, "백엔드",
                RecruitmentStatus.IN_PROGRESS, STAGE, List.of(new StageInfo(STAGE, recruitmentId, 2, "1차 면접",
                        StageType.INTERVIEW, StageStatus.ACTIVE, null, null, null, null)),
                Instant.now(), Instant.now(), null));
        InterviewService interviews = mock(InterviewService.class);
        when(interviews.view(COMPANY, STAGE, APPLICATION)).thenAnswer(call -> new InterviewView(APPLICATION, null,
                List.of(new InterviewView.Question(UUID.randomUUID(), "가장 어려웠던 장애 대응은?",
                        QuestionSource.MANUAL, answer)), List.of()));
        InterviewAnalyst queued = input -> {
            analyzed.add(input);
            open = true;
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
        listener = new InterviewAnalysisListener(interviews, recruits, queued, jobs);
    }

    @Test
    @DisplayName("분석 중에 답변이 여러 번 바뀌면 끝난 뒤 마지막 기록으로 한 번만 다시 분석한다")
    void coalescesChangesWhileRunning() {
        listener.on(CHANGED);
        answer = "둘째 답변";
        listener.on(CHANGED);
        answer = "셋째 답변";
        listener.on(CHANGED);

        assertThat(analyzed).hasSize(1);
        assertThat(analyzed.getFirst().stageName()).isEqualTo("1차 면접");
        assertThat(analyzed.getFirst().questions().getFirst().answer()).isEqualTo("첫 답변");

        finish();

        assertThat(analyzed).hasSize(2);
        assertThat(analyzed.getLast().questions().getFirst().answer()).isEqualTo("셋째 답변");

        finish();

        assertThat(analyzed).hasSize(2);
    }

    @Test
    @DisplayName("작업을 잃어 열린 작업이 없으면 바로 다시 분석한다")
    void analyzesAgainWhenJobWasLost() {
        listener.on(CHANGED);
        open = false;
        listener.on(CHANGED);

        assertThat(analyzed).hasSize(2);
    }

    @Test
    @DisplayName("다른 작업의 결과는 무시한다")
    void ignoresOtherJobs() {
        listener.on(CHANGED);
        listener.on(CHANGED);

        listener.on(new JobFinished(new JobResult(UUID.randomUUID(), "assessment/analyze", APPLICATION.toString(),
                JobStatus.DONE, null, null)));

        assertThat(analyzed).hasSize(1);
    }

    private void finish() {
        open = false;
        listener.on(new JobFinished(new JobResult(UUID.randomUUID(), InterviewAnalyst.ANALYZE_JOB,
                InterviewAnalyst.jobTarget(COMPANY, STAGE, APPLICATION), JobStatus.DONE, null, null)));
    }
}
