package com.hiremate.apply;

import com.fasterxml.jackson.annotation.JsonIgnore;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 전형 화면의 지원자 한 명. 분석 전이면 경력이 null이다. 서류는 점수를 매기지 않는다.
 * 블라인드 채용에서 마지막 전형 결과를 확정하기 전이면 name은 "지원자 12" 같은 지원번호 이름이고 email은 비어 있다.
 * 메일을 보낼 때는 {@link ApplicantContact}를 쓴다.
 *
 * @param shortfalls 채우지 못했거나 확인이 필요한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요)
 * @param criterionMarks 평가 항목 ID별 판정. 분석 전이면 비어 있다
 * @param highTalents 상으로 판정한 인재상 제목. 판정 전이면 비어 있다 (항목별 판정과 함께 backend 안에서만 쓴다)
 * @param midTalents 중으로 판정한 인재상 제목. 판정 전이면 비어 있다
 */
public record ApplicantInfo(UUID applicationId, UUID recruitmentId, int applicationNo, String name, String email,
        @Schema(nullable = true) Integer careerYears, @Schema(nullable = true) String lastCompany,
        List<String> shortfalls, AnalysisStatus analysisStatus, Instant submittedAt,
        @JsonIgnore Map<String, CriterionMark> criterionMarks, @JsonIgnore List<String> highTalents,
        @JsonIgnore List<String> midTalents) {

    public ApplicantInfo {
        shortfalls = shortfalls == null ? List.of() : List.copyOf(shortfalls);
        criterionMarks = criterionMarks == null ? Map.of() : Map.copyOf(criterionMarks);
        highTalents = highTalents == null ? List.of() : List.copyOf(highTalents);
        midTalents = midTalents == null ? List.of() : List.copyOf(midTalents);
    }

    /** 항목별 판정이 없는 지원자 (테스트). */
    public ApplicantInfo(UUID applicationId, UUID recruitmentId, int applicationNo, String name, String email,
            Integer careerYears, String lastCompany, List<String> shortfalls, AnalysisStatus analysisStatus,
            Instant submittedAt) {
        this(applicationId, recruitmentId, applicationNo, name, email, careerYears, lastCompany, shortfalls,
                analysisStatus, submittedAt, Map.of(), List.of(), List.of());
    }

    /** 블라인드 채용에서 이름 대신 부르는 말. 마지막 전형 결과를 확정하기 전까지 쓴다. */
    public static String blindName(int applicationNo) {
        return "지원자 " + applicationNo;
    }
}
