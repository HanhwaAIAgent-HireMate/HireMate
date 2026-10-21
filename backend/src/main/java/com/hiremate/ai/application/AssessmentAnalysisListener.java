package com.hiremate.ai.application;

import com.hiremate.assessment.AssessmentArea;
import com.hiremate.assessment.AssessmentResultRecorded;
import com.hiremate.assessment.AssessmentResultView;
import com.hiremate.assessment.AssessmentService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageInfo;
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/**
 * 평가 결과가 등록되면 Assessment Agent로 분석해 둔다. Chat이 평가 자료를 물을 때 원문을 다시 읽지 않기 위해서다.
 * 실패하면 이벤트가 완료되지 않은 채 남아 다시 보낼 수 있다. 점수 · 결정은 바꾸지 않는다.
 */
@Component
class AssessmentAnalysisListener {

    private final AssessmentService assessments;
    private final RecruitService recruits;
    private final AssessmentAgent agent;

    AssessmentAnalysisListener(AssessmentService assessments, RecruitService recruits, AssessmentAgent agent) {
        this.assessments = assessments;
        this.recruits = recruits;
        this.agent = agent;
    }

    @ApplicationModuleListener
    void on(AssessmentResultRecorded event) {
        assessments.find(event.companyId(), event.stageId(), event.applicationId()).ifPresent(result -> {
            String stageName = recruits.getByStage(event.companyId(), event.stageId()).stage(event.stageId())
                    .map(StageInfo::name)
                    .orElse("평가 전형");
            // PDF 본문 추출은 apply 모듈 안에만 있어 아직 보내지 않는다. 파일 본문은 다음 단계에서 넣는다
            agent.analyze(new AssessmentInput(event.companyId(), event.recruitmentId(), event.stageId(),
                    event.applicationId(), stageName, result.total(), areas(result), result.grade(), null,
                    result.url(), result.note()));
        });
    }

    /** NCS 영역은 점수가 없어도 null로 넣어 ai 서버가 '점수 없음'을 알 수 있게 한다. */
    static Map<String, BigDecimal> areas(AssessmentResultView result) {
        Map<String, BigDecimal> areas = new LinkedHashMap<>();
        AssessmentArea.NCS.forEach(area -> areas.put(area, result.areas().get(area)));
        result.areas().forEach(areas::putIfAbsent);
        return areas;
    }
}
