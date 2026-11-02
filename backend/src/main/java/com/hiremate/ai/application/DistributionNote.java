package com.hiremate.ai.application;

import java.util.List;
import java.util.Map;

/**
 * 서류 전형 분포 해설 (ai의 DistributionNote). Report Agent가 분포 숫자를 읽고 담당자가 먼저 볼 점을 쓴 두세 문장(lines)과,
 * 차트마다 그 차트에서 읽을 점 한 문장(charts)이다. charts의 키는 funnel · required · counts · criteria · careers다.
 * ai가 리포트 문장 검사를 거친 문장만 돌려준다. 만들지 못하면 비어 있고 화면은 숫자 요약만 보여 준다.
 */
public record DistributionNote(List<String> lines, Map<String, String> charts) {

    public static final DistributionNote EMPTY = new DistributionNote(List.of(), Map.of());

    public DistributionNote {
        lines = lines == null ? List.of() : List.copyOf(lines);
        charts = charts == null ? Map.of() : Map.copyOf(charts);
    }
}
