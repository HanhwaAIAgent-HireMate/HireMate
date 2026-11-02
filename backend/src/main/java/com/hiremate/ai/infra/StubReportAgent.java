package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ComposedReport;
import com.hiremate.ai.application.DistributionNote;
import com.hiremate.ai.application.ReportAgent;
import com.hiremate.ai.application.ReportBundle;
import com.hiremate.ai.application.ReportDistribution;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 개발용 Report Agent. 모델을 부르지 않고 지표 칸과 점수 분포만 있는 설계서를 바로 돌려준다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.REPORT, mode = AiMode.STUB)
class StubReportAgent implements ReportAgent {

    private final JsonMapper json;

    StubReportAgent(JsonMapper json) {
        this.json = json;
    }

    /** 개발용 설계서. 지표 칸과 첫 숫자 값의 분포만 그린다. 모델을 부르지 않는다. */
    @Override
    public Optional<ComposedReport> compose(UUID reportId, ReportBundle bundle) {
        ObjectNode spec = json.createObjectNode();
        spec.put("title", bundle.title() + " 리포트");
        spec.put("summary", "개발용 Report Agent가 만든 리포트예요. 숫자는 기록 그대로예요.");
        spec.putArray("skills");
        ArrayNode sections = spec.putArray("sections");
        ObjectNode section = sections.addObject();
        section.put("title", "한눈에 보기");
        section.putNull("area");
        section.put("takeaway", "대상 " + bundle.applicants().size() + "명의 기록이에요.");
        ArrayNode blocks = section.putArray("blocks");
        ObjectNode kpi = blocks.addObject();
        kpi.put("type", "kpi");
        kpi.put("title", "주요 지표");
        kpi.put("caption", "전형 결과의 인원이에요.");
        ArrayNode metrics = kpi.putArray("metrics");
        bundle.metrics().stream().limit(4).forEach(metric -> metrics.add(metric.id()));
        if (bundle.totalKey() != null) {
            ObjectNode distribution = blocks.addObject();
            distribution.put("type", "distribution");
            distribution.put("title", "점수 분포");
            distribution.put("caption", "전형 전체의 점수 분포예요.");
            distribution.put("key", bundle.totalKey());
            distribution.putArray("highlight");
            distribution.putArray("reference");
            distribution.putNull("split");
        }
        return Optional.of(new ComposedReport(spec, List.of(), List.of(), true, null, List.of()));
    }

    /** 개발용은 모델을 부르지 않아 해설이 없다. 화면은 숫자 요약만 보여 준다. */
    @Override
    public DistributionNote explain(ReportDistribution.ForAi distribution) {
        return DistributionNote.EMPTY;
    }
}
