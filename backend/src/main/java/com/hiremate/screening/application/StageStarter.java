package com.hiremate.screening.application;

import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.posting.PostingClosed;
import com.hiremate.screening.ScreeningService;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** 공고가 마감되면 같은 트랜잭션에서 첫 전형에 지원자 전원을 넣는다. 마감 직후 전형 화면이 비어 보이지 않게 한다. */
@Component
class StageStarter {

    private final ScreeningService screening;
    private final ApplicationService applications;

    StageStarter(ScreeningService screening, ApplicationService applications) {
        this.screening = screening;
        this.applications = applications;
    }

    @EventListener
    void on(PostingClosed event) {
        screening.startStage(event.companyId(), event.firstStageId(),
                applications.applicants(event.companyId(), event.recruitmentId()).stream()
                        .map(ApplicantInfo::applicationId)
                        .toList());
    }
}
