package com.hiremate.ai.application;

import com.hiremate.interview.InterviewAnswersChanged;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import com.hiremate.job.JobFinished;
import com.hiremate.job.JobQueue;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/**
 * 면접 답변이 바뀌면 Interview Agent가 확인된 점과 확인되지 않은 점을 프로필에 정리한다 (FR-28). 결정은 바꾸지 않는다.
 *
 * <p>답변은 질문마다 따로 저장되어 면접 한 번에 여러 번 바뀐다. 같은 지원자 · 전형의 분석 작업이 아직 끝나지 않았으면
 * 새로 넣지 않고, 끝난 뒤 그때의 기록으로 한 번 더 분석한다. 작업을 잃어 열린 작업이 없으면 바로 다시 넣는다.
 * 이 표시는 서버 메모리에 두므로 backend를 다시 띄우면 다음 답변부터 새로 센다.
 */
@Component
class InterviewAnalysisListener {

    private final InterviewService interviews;
    private final RecruitService recruits;
    private final InterviewAnalyst analyst;
    private final JobQueue jobs;
    private final Set<String> running = new HashSet<>();
    private final Set<String> changedWhileRunning = new HashSet<>();

    InterviewAnalysisListener(InterviewService interviews, RecruitService recruits, InterviewAnalyst analyst,
            JobQueue jobs) {
        this.interviews = interviews;
        this.recruits = recruits;
        this.analyst = analyst;
        this.jobs = jobs;
    }

    @ApplicationModuleListener
    synchronized void on(InterviewAnswersChanged event) {
        String target = InterviewAnalyst.jobTarget(event.companyId(), event.stageId(), event.applicationId());
        if (running.contains(target) && jobs.isOpen(InterviewAnalyst.ANALYZE_JOB, target)) {
            changedWhileRunning.add(target);
            return;
        }
        analyze(event.companyId(), event.stageId(), event.applicationId());
    }

    @ApplicationModuleListener
    synchronized void on(JobFinished event) {
        if (!InterviewAnalyst.ANALYZE_JOB.equals(event.result().type())) {
            return;
        }
        String target = event.result().target();
        running.remove(target);
        if (changedWhileRunning.remove(target)) {
            String[] ids = target.split(":", 3);
            analyze(UUID.fromString(ids[0]), UUID.fromString(ids[1]), UUID.fromString(ids[2]));
        }
    }

    private void analyze(UUID companyId, UUID stageId, UUID applicationId) {
        if (analyst.analyze(input(companyId, stageId, applicationId)).isEmpty()) {
            running.add(InterviewAnalyst.jobTarget(companyId, stageId, applicationId));
        }
    }

    private InterviewAnalysisInput input(UUID companyId, UUID stageId, UUID applicationId) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        String stageName = recruitment.stage(stageId).map(StageInfo::name).orElse("면접 전형");
        InterviewView view = interviews.view(companyId, stageId, applicationId);
        List<InterviewAnalysisInput.PreviousInterview> previous = view.previous().stream()
                .map(interview -> new InterviewAnalysisInput.PreviousInterview(interview.stageName(),
                        answered(interview.questions())))
                .toList();
        return new InterviewAnalysisInput(companyId, recruitment.id(), stageId, applicationId, stageName,
                answered(view.questions()), previous);
    }

    private static List<InterviewAnalysisInput.AnsweredQuestion> answered(List<InterviewView.Question> questions) {
        return questions.stream()
                .map(question -> new InterviewAnalysisInput.AnsweredQuestion(question.text(), question.answer()))
                .toList();
    }
}
