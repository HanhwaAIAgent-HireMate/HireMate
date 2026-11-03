package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.Decision;
import java.util.List;
import java.util.UUID;
import java.util.stream.IntStream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class ReportDistributionsTests {

    private static CandidateRow above(int metCount) {
        return new CandidateRow(UUID.randomUUID(), "지원자", 3, null, Decision.PENDING, false, false, true, null,
                AnalysisStatus.DONE, List.of(), metCount, 10, 0, 0, List.of());
    }

    private static List<CandidateRow> rows(int... metCounts) {
        return IntStream.of(metCounts).mapToObj(ReportDistributionsTests::above).toList();
    }

    @Test
    @DisplayName("목표 인원번째와 개수가 같은 줄의 처음과 끝, 그중 목표 안에 드는 인원을 센다")
    void cutFindsTheTieAroundTheTarget() {
        var cut = ReportDistributions.cut(rows(9, 9, 8, 8, 8, 8, 7), 4, CandidateRow::metCount);

        assertThat(cut).isEqualTo(new ReportDistribution.Cut(8, 3, 6, 2));
    }

    @Test
    @DisplayName("선 위가 목표 인원 이하면 선발 경계가 없다")
    void noCutWhenAboveLineFitsTheTarget() {
        assertThat(ReportDistributions.cut(rows(9, 8, 7), 3, CandidateRow::metCount)).isNull();
    }

    @Test
    @DisplayName("결정을 볼 수 없는 구성원에게는 합격 처리 인원을 빼고 준다")
    void hideDecisionDropsThePassCount() {
        var distribution = new ReportDistribution(UUID.randomUUID(), 300, 300, 97, 60, 60, 6, 10, null,
                new ReportDistribution.Required(97, 16, 187, List.of()), List.of(), List.of(), null, List.of(), 5,
                List.of(), 35);

        assertThat(distribution.passed()).isEqualTo(35);
        assertThat(distribution.hideDecision().passed()).isNull();
        assertThat(distribution.hideDecision().aboveLine()).isEqualTo(97);
    }

    @Test
    @DisplayName("Report Agent에 보내는 분포는 경계 그룹의 인원만 남기고 지원자는 넣지 않는다")
    void forAiKeepsGroupSizesWithoutPeople() {
        var person = new ReportDistribution.Person(UUID.randomUUID(), "김지원", 3, 4, 10, 0, 5, 1, List.of());
        var distribution = new ReportDistribution(UUID.randomUUID(), 300, 300, 97, 60, 60, 6, 10, null,
                new ReportDistribution.Required(97, 16, 187, List.of()), List.of(), List.of(), null,
                List.of(new ReportDistribution.Group("selection-edge", "선발 경계", "개수가 같아요", List.of(person, person))),
                5, List.of(), 35);

        var facts = distribution.forAi();

        assertThat(facts.groups()).containsExactly(new ReportDistribution.GroupCount("선발 경계", "개수가 같아요", 2));
        assertThat(facts.toString()).doesNotContain("김지원");
        assertThat(facts.passed()).isEqualTo(35);
    }
}
