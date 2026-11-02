package com.hiremate.ai.application;

import com.hiremate.posting.ScreeningRubric;
import com.hiremate.screening.CandidateSort;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.UUID;

/**
 * 서류 전형 분포 리포트 (RPT-01). 전형 전체 지원자의 판정을 코드가 센다. 모델을 부르지 않고, 같은 자료면 같은 결과다.
 * 순위나 합격 · 불합격 제안은 넣지 않는다. 경계 그룹은 담당자가 심층 분석으로 다시 볼 사람을 모은 것이다.
 *
 * @param total 전형 지원자 수
 * @param analyzed 서류 분석이 끝난 지원자 수
 * @param aboveLine 선 위(필수 조건 모두 충족 또는 담당자가 올림) 지원자 수
 * @param target 서류 통과 목표 인원. 요청에 없으면 defaultTarget이다
 * @param defaultTarget 공고 채용 인원 × targetMultiplier
 * @param hireCount 공고 채용 인원. 공고에 없으면 평가 기준의 선발 인원이다
 * @param targetMultiplier 기본 목표 인원 배수 (설정 hiremate.report.distribution.target-multiplier)
 * @param sort 선 위 개수를 센 기준. BASIC은 자격요건 + 우대사항 충족 개수, TALENT는 여기에 인재상 상 개수를 더한다
 * @param required 필수 조건 판정별 인원
 * @param criteria 평가 항목마다 분석이 끝난 지원자의 판정 인원. 공고 기준 순서다
 * @param counts 선 위 지원자의 개수별 인원. 개수가 많은 순이다
 * @param cut 목표 인원에서 개수가 같은 구간. 선 위가 목표 인원보다 많을 때만 있다
 * @param groups 경계 그룹 (선발 경계, 선 아래 다시 볼 사람)
 * @param deepSize 심층 분석 한 번에 보는 인원 (설정 hiremate.report.distribution.deep-size)
 * @param careers 경력 구간별 인원 (전체, 선 위)
 * @param passed 담당자가 합격 처리한 인원. 목표 인원과 견주어 보여 주고 합격을 막지 않는다. HR이 아니면 null이다
 */
public record ReportDistribution(UUID stageId, int total, int analyzed, int aboveLine, int target, int defaultTarget,
        int hireCount, int targetMultiplier, CandidateSort sort, Required required, List<CriterionStat> criteria,
        List<CountBucket> counts, @Schema(nullable = true) Cut cut, List<Group> groups, int deepSize,
        List<CareerBand> careers, @Schema(nullable = true) Integer passed) {

    /**
     * Report Agent에 보내는 분포. 경계 그룹은 인원만 남기고 지원자(이름 · 지원서 ID)는 넣지 않는다.
     */
    public ForAi forAi() {
        return new ForAi(total, analyzed, aboveLine, target, passed, required, criteria,
                groups.stream().map(group -> new GroupCount(group.label(), group.reason(), group.people().size()))
                        .toList(),
                careers, counts, cut);
    }

    /** Report Agent에 보내는 분포 (ai의 DistributionFacts). counts · cut은 충족 개수 차트의 자료다. */
    public record ForAi(int total, int analyzed, int aboveLine, int target, @Schema(nullable = true) Integer passed,
            Required required, List<CriterionStat> criteria, List<GroupCount> groups, List<CareerBand> careers,
            List<CountBucket> counts, @Schema(nullable = true) Cut cut) {
    }

    /** 경계 그룹의 이름 · 까닭 · 인원. */
    public record GroupCount(String label, String reason, int size) {
    }

    /** 결정을 볼 수 없는 구성원에게 줄 분포. 합격 처리 인원을 뺀다. */
    public ReportDistribution hideDecision() {
        return new ReportDistribution(stageId, total, analyzed, aboveLine, target, defaultTarget, hireCount,
                targetMultiplier, sort, required, criteria, counts, cut, groups, deepSize, careers, null);
    }

    /**
     * 필수 조건 판정별 인원. 미충족은 하나라도 미충족 · 부분 충족, 확인 필요는 확인 필요만 남았거나 분석 전이다.
     *
     * @param criterionIds 필수로 체크한 평가 항목 ID
     */
    public record Required(int met, int unmet, int unknown, List<String> criterionIds) {
    }

    /** 평가 항목 하나의 판정 인원. */
    public record CriterionStat(String criterionId, ScreeningRubric.Category category, String text,
            boolean required, int met, int partial, int notMet, int unknown) {
    }

    /** 선 위 지원자 중 충족 개수가 value인 인원. */
    public record CountBucket(int value, int count) {
    }

    /**
     * 목표 인원 자리에서 개수가 같은 구간.
     *
     * @param value 목표 인원번째 지원자의 개수
     * @param from 그 개수인 첫 지원자의 줄 번호 (1부터)
     * @param to 그 개수인 마지막 지원자의 줄 번호
     * @param inside 그중 목표 인원 안에 드는 인원
     */
    public record Cut(int value, int from, int to, int inside) {
    }

    /**
     * 경계 그룹.
     *
     * @param id selection-edge(선발 경계) 또는 below-line(선 아래 다시 볼 사람)
     * @param reason 이 그룹에 든 까닭. 코드가 정한 규칙 그대로다
     * @param people 확인 필요가 많은 순, 같으면 부분 충족이 많은 순이다
     */
    public record Group(String id, String label, String reason, List<Person> people) {
    }

    /**
     * 경계 그룹의 지원자 한 명.
     *
     * @param metCount 자격요건 + 우대사항 충족 개수
     * @param unknownCount 확인 필요 판정 개수
     * @param partialCount 부분 충족 판정 개수
     * @param missingRequired 충족하지 못했거나 확인이 필요한 필수 조건의 항목 글
     */
    public record Person(UUID applicationId, String name, @Schema(nullable = true) Integer careerYears,
            int metCount, int criterionTotal, int talentCount, int unknownCount, int partialCount,
            List<String> missingRequired) {
    }

    /** 경력 구간 하나의 인원. */
    public record CareerBand(String label, int all, int aboveLine) {
    }
}
