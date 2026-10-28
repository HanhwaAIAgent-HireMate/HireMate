package com.hiremate.ai.application;

import com.hiremate.assessment.AssessmentArea;
import com.hiremate.assessment.AssessmentResultRecorded;
import com.hiremate.assessment.AssessmentResultView;
import com.hiremate.assessment.AssessmentService;
import com.hiremate.file.FileService;
import com.hiremate.file.PdfText;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageInfo;
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/**
 * 평가 결과가 등록되면 Assessment Agent로 분석해 둔다. Chat이 평가 자료를 물을 때 원문을 다시 읽지 않기 위해서다.
 * remote면 분석 작업을 대기열에 넣고 AI 워커가 프로필에 저장한다. 작업을 넣지 못하면 이벤트가 완료되지 않은 채 남아 다시
 * 보낼 수 있다. 점수 · 결정은 바꾸지 않는다. 결과 리포트나 과제 제출 PDF가 있으면 본문을 꺼내 함께 보낸다.
 */
@Component
class AssessmentAnalysisListener {

    private final AssessmentService assessments;
    private final RecruitService recruits;
    private final AssessmentAgent agent;
    private final FileService files;

    AssessmentAnalysisListener(AssessmentService assessments, RecruitService recruits, AssessmentAgent agent,
            FileService files) {
        this.assessments = assessments;
        this.recruits = recruits;
        this.agent = agent;
        this.files = files;
    }

    @ApplicationModuleListener
    void on(AssessmentResultRecorded event) {
        assessments.find(event.companyId(), event.stageId(), event.applicationId()).ifPresent(result -> {
            String stageName = recruits.getByStage(event.companyId(), event.stageId()).stage(event.stageId())
                    .map(StageInfo::name)
                    .orElse("평가 전형");
            agent.analyze(new AssessmentInput(event.companyId(), event.recruitmentId(), event.stageId(),
                    event.applicationId(), stageName, result.total(), areas(result), result.grade(),
                    submission(event.companyId(), result), result.url(), result.note()));
        });
    }

    /**
     * 올린 PDF의 파일 이름과 본문. 파일이 없으면 null이다. 글자를 읽지 못한 PDF면 본문이 빈 문자열이고,
     * ai 서버는 빈 본문을 분석 자료로 쓰지 않는다.
     */
    private AssessmentInput.Submission submission(UUID companyId, AssessmentResultView result) {
        if (result.fileId() == null) {
            return null;
        }
        byte[] pdf = files.read(companyId, result.fileId()).bytes();
        return new AssessmentInput.Submission(result.fileName(), PdfText.extract(pdf));
    }

    /** NCS 영역은 점수가 없어도 null로 넣어 ai 서버가 '점수 없음'을 알 수 있게 한다. */
    static Map<String, BigDecimal> areas(AssessmentResultView result) {
        Map<String, BigDecimal> areas = new LinkedHashMap<>();
        AssessmentArea.NCS.forEach(area -> areas.put(area, result.areas().get(area)));
        result.areas().forEach(areas::putIfAbsent);
        return areas;
    }
}
