package com.hiremate.ai.application;

import com.hiremate.recruit.RecruitmentClosed;
import com.hiremate.recruit.StageConfirmed;
import com.hiremate.report.AgentReportKind;
import java.util.List;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/**
 * 서류 전형 결과를 확정하면 전형 결과 리포트를, 채용을 종료하면 최종 리포트를 Report Agent가 쓴다. 리포트는 채용 상태를 바꾸지
 * 않는다.
 */
@Component
class AgentReportListener {

    private final ReportComposer composer;

    AgentReportListener(ReportComposer composer) {
        this.composer = composer;
    }

    @ApplicationModuleListener
    void on(StageConfirmed event) {
        // 직무역량 평가 · 면접 전형은 전형 결과 리포트를 쓰지 않는다 (채용 최종 리포트가 모은다)
        if (composer.documentStage(event.companyId(), event.stageId())) {
            composer.request(event.companyId(), event.stageId(), AgentReportKind.STAGE, List.of(), "", false, null);
        }
    }

    @ApplicationModuleListener
    void on(RecruitmentClosed event) {
        composer.requestFinal(event.companyId(), event.recruitmentId(), null);
    }
}
