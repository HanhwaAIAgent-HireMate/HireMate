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
                AnalysisStatus.DONE, false, List.of(), null, null, null, 0, null, 0, metCount, 10, 0, 0, List.of());
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
}
