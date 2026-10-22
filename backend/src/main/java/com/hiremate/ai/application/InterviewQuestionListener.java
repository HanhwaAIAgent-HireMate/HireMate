package com.hiremate.ai.application;

import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageConfirmed;
import com.hiremate.recruit.StageFinished;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.ScreeningService;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/**
 * 전형 결과를 확정하면 다음 면접의 합격자 질문을 미리 만든다. 다음 전형을 시작할 때는 준비하지 못한 질문을 다시 맡긴다.
 * 면접관이 카드를 열었을 때 질문이 이미 들어 있게 한다. 만들지 못한 지원자는 AI Chat으로 다시 요청할 수 있어 로그만 남긴다.
 */
@Component
class InterviewQuestionListener {

    private static final Logger log = LoggerFactory.getLogger(InterviewQuestionListener.class);

    private final RecruitService recruits;
    private final ScreeningService screening;
    private final InterviewAiService interviews;

    InterviewQuestionListener(RecruitService recruits, ScreeningService screening, InterviewAiService interviews) {
        this.recruits = recruits;
        this.screening = screening;
        this.interviews = interviews;
    }

    @ApplicationModuleListener
    void on(StageConfirmed event) {
        prepare(event.companyId(), event.stageId());
    }

    @ApplicationModuleListener
    void on(StageFinished event) {
        prepare(event.companyId(), event.stageId());
    }

    private void prepare(UUID companyId, UUID confirmedStageId) {
        Optional<StageInfo> next = nextStage(recruits.getByStage(companyId, confirmedStageId), confirmedStageId);
        if (next.isEmpty() || next.get().type() != StageType.INTERVIEW) {
            return;
        }
        UUID stageId = next.get().id();
        for (UUID applicationId : screening.results(companyId, confirmedStageId).passed()) {
            try {
                interviews.prepare(companyId, stageId, applicationId);
            } catch (RuntimeException exception) {
                log.warn("Interview questions were not prepared for {} in stage {}", applicationId, stageId, exception);
            }
        }
    }

    /** 끝난 전형 바로 다음 전형. 마지막 전형이면 빈 값이다. */
    private static Optional<StageInfo> nextStage(RecruitmentInfo recruitment, UUID finishedStageId) {
        List<StageInfo> stages = recruitment.stages();
        for (int index = 0; index < stages.size() - 1; index++) {
            if (stages.get(index).id().equals(finishedStageId)) {
                return Optional.of(stages.get(index + 1));
            }
        }
        return Optional.empty();
    }
}
