package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.ReportAgent;
import com.hiremate.ai.application.ReportInput;
import com.hiremate.report.ReportContent;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 개발용 Report Agent. 확정 결과의 숫자와 분석 근거를 그대로 옮겨 요약한다. 근거가 없으면 없다고 적는다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.REPORT, mode = AiMode.STUB)
class StubReportAgent implements ReportAgent {

    @Override
    public Optional<ReportContent> write(UUID companyId, UUID recruitmentId, ReportInput input) {
        long finalCount = input.finalists().size();
        String summary = "지원자 " + input.applicantCount() + "명 중 **" + finalCount
                + "명**을 최종 합격으로 결정했어요. 전형 " + input.stages().size()
                + "개를 거쳤고, 최종 안내 발송까지 마쳤어요.";
        List<ReportContent.Finalist> finalists = input.finalists().stream().map(finalist -> {
            List<String> sources = new ArrayList<>(finalist.notable().stream()
                    .map(CandidateAnalysis.Finding::source).distinct().toList());
            String reason = finalist.notable().isEmpty()
                    ? "제출 문서에서 뚜렷한 근거를 찾지 못했어요. 전형 기록을 확인해 주세요."
                    : String.join(", ", finalist.notable().stream().limit(2)
                            .map(CandidateAnalysis.Finding::text)
                            .toList());
            if (!finalist.memos().isEmpty()) {
                sources.add("전형 메모");
            }
            return new ReportContent.Finalist(finalist.name(), reason, sources);
        }).toList();
        List<String> notes = new ArrayList<>();
        long undecided = input.undecided().stream().mapToLong(Long::longValue).sum();
        if (undecided > 0) {
            notes.add("결정하지 않아 불합격으로 확정된 지원자가 전형 전체에서 " + undecided + "명 있었어요.");
        }
        List<ReportContent.ReportStage> counted = input.stages().stream()
                .filter(stage -> stage.target() > 0)
                .toList();
        // 전형이 하나면 견줄 전형이 없어 '가장 낮았다'고 쓰지 않는다
        if (counted.size() >= 2) {
            counted.stream()
                    .min((left, right) -> Double.compare((double) left.pass() / left.target(),
                            (double) right.pass() / right.target()))
                    .ifPresent(stage -> notes.add(stage.name() + "의 합격률이 "
                            + Math.round(100.0 * stage.pass() / stage.target()) + "%로 가장 낮았어요."));
        }
        return Optional.of(new ReportContent(summary, input.applicantCount(), finalCount, input.stages(), finalists,
                notes));
    }
}
