package com.hiremate.ai.application;

import com.hiremate.recruit.StageType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Report Agent가 읽는 데이터 묶음 (ai의 ReportBundle). 숫자는 모두 backend가 계산한 값이고, 지원자는 지원자번호(A-0017)로만
 * 나온다. 이름은 넣지 않는다. 분석 판정 · 근거는 ai가 자기 저장소에서 applicationId로 찾아 붙인다.
 *
 * @param targets 비교 리포트의 비교 대상 지원자번호. 전형 · 최종 리포트면 빈 목록
 * @param focus 요청에서 뽑은 관점 (예: 협업). 없으면 빈 문자열
 * @param brief Chat 요청이 '간략히'였는가
 * @param totalKey 현재 전형 총점 값 key
 * @param areas 현재 전형의 평가 영역. 리포트는 영역마다 섹션을 둔다
 */
public record ReportBundle(Kind kind, UUID companyId, UUID recruitmentId, UUID stageId, String title, Instant asOf,
        String focus, boolean brief, List<Stage> stages, List<Applicant> applicants, List<String> targets,
        @Schema(nullable = true) String totalKey, List<Area> areas, List<Metric> metrics, List<Fact> facts,
        List<Evidence> evidence) {

    /** 리포트 종류. STAGE는 결과 확정 때 만드는 전형 결과, COMPARE는 Chat에서 요청한 지원자 비교, FINAL은 채용 최종 리포트 */
    public enum Kind {
        STAGE,
        COMPARE,
        FINAL
    }

    /** 범위 안의 전형 하나. confirmedAt이 없으면 진행 중인 전형이다. */
    public record Stage(UUID stageId, String name, StageType type, @Schema(nullable = true) Instant confirmedAt) {
    }

    /** 대상 지원자. number는 채용 안에서 모든 전형에 같은 지원자번호다. */
    public record Applicant(String number, @Schema(nullable = true) UUID applicationId,
            @Schema(nullable = true) Integer careerYears, @Schema(nullable = true) String lastCompany) {
    }

    /**
     * backend가 집계한 지표 하나.
     *
     * @param key 이 지표가 집계한 값 key (예: 평균 총점은 document.total). 막대의 기준선으로 쓴다
     * @param group 같은 group 지표를 합치면 전체가 된다 (도넛 · 구성 막대 조각)
     */
    public record Metric(String id, @Schema(nullable = true) UUID stageId, String label, double value, String unit,
            @Schema(nullable = true) String key, @Schema(nullable = true) String group) {
    }

    /** 지원자 한 명의 값 하나. value가 숫자면 점수, 글이면 판정(PASS · MET · RECOMMENDED 등)이다. */
    public record Fact(String id, String applicant, UUID stageId, String key, String label, Object value,
            @Schema(nullable = true) Double max) {
    }

    /**
     * 근거 하나. text는 분석 Agent의 판단이고 quote는 그 판단의 원문 문장(글자 그대로)이다. agent는 그 근거를 만든 분석 Agent다.
     *
     * @param quote 원문 문장. 원문이 없는 판단이면 null
     * @param label 근거가 받치는 항목 이름 (서류 평가 항목, 강점 · 확인할 점)
     * @param verdict 그 항목의 판정 코드 (MET · PARTIAL 등)
     * @param strength 원문의 강도. QUANT는 성과를 숫자와 단위로 적은 문장, CLAIM은 한 일만 적은 문장이다. ai가 붙이고 원문이
     *     없으면 null이다
     */
    public record Evidence(String id, String applicant, UUID stageId, String agent, String text, String source,
            @Schema(nullable = true) String quote, @Schema(nullable = true) String label,
            @Schema(nullable = true) String verdict, @Schema(nullable = true) String strength) {
    }

    /** 평가 영역 하나. scoreKey는 영역 점수 값 key, keys는 영역 항목 값 key(판정)다. */
    public record Area(String id, String label, @Schema(nullable = true) String scoreKey, List<String> keys) {
    }
}
