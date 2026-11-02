package com.hiremate.interview.application;

import com.hiremate.interview.InterviewScheduleRequested;
import com.hiremate.interview.InterviewScheduling;
import com.hiremate.recruit.StageConfirmed;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/** 확정 트랜잭션에서는 대기 상태만 기록하고, 커밋된 뒤 독립 트랜잭션에서 시간을 배정한다. */
@Component
class InterviewSchedulingListener {

    private static final Logger log = LoggerFactory.getLogger(InterviewSchedulingListener.class);

    private final InterviewScheduling scheduling;

    InterviewSchedulingListener(InterviewScheduling scheduling) {
        this.scheduling = scheduling;
    }

    @EventListener
    public void confirmed(StageConfirmed event) {
        scheduling.request(event.companyId(), event.stageId());
    }

    @ApplicationModuleListener
    public void requested(InterviewScheduleRequested event) {
        try {
            scheduling.execute(event.companyId(), event.previousStageId());
        } catch (RuntimeException exception) {
            log.warn("Interview scheduling failed for stage {}", event.previousStageId(), exception);
            scheduling.failed(event.companyId(), event.previousStageId(), exception);
        }
    }
}
