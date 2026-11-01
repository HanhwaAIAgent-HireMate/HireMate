package com.hiremate.apply.domain;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.CriterionMark;
import com.hiremate.apply.QualificationStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "applications")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class JobApplication {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID recruitmentId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private UUID postingId;

    @Column(nullable = false)
    private int applicationNo;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(nullable = false, length = 254)
    private String email;

    @Column(nullable = false, length = 30)
    private String phone;

    private String certificates;

    @Column(nullable = false)
    private boolean consentPrivacy;

    @Column(nullable = false)
    private boolean consentAi;

    @Column(nullable = false)
    private Instant submittedAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private AnalysisStatus analysisStatus;

    private Integer careerYears;

    private String lastCompany;

    /** 서류 평가 총점 (자격요건 + 우대사항, 0~100, 소수 첫째 자리). */
    @Column(precision = 4, scale = 1)
    private BigDecimal documentScore;

    /** 확인 필요를 0점으로 넣어 계산한 총점(보류 점수). 확인 필요가 없으면 documentScore와 같다. */
    @Column(precision = 4, scale = 1)
    private BigDecimal documentScoreLow;

    /** 자격요건 75% 통과가 확정됐는가 (qualificationStatus가 PASSED). */
    @Column(nullable = false)
    private boolean scorePassed;

    /** 총점을 보류했는가. 보류면 documentScore가 null이다. */
    @Column(nullable = false)
    private boolean scoreHeld;

    /** 자격요건 75% 통과 판단. 분석 전이면 UNDETERMINED다. */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private QualificationStatus qualificationStatus = QualificationStatus.UNDETERMINED;

    @Column(precision = 4, scale = 1)
    private BigDecimal qualificationRate;

    @Column(precision = 4, scale = 1)
    private BigDecimal qualificationScore;

    /** 확인 필요를 0점으로 넣어 계산한 자격요건 점수. 자격요건 순 정렬에 쓴다. */
    @Column(precision = 4, scale = 1)
    private BigDecimal qualificationScoreLow;

    @Column(nullable = false)
    private int qualificationMax;

    @Column(precision = 4, scale = 1)
    private BigDecimal preferenceScore;

    @Column(nullable = false)
    private int preferenceMax;

    /** 평가에 쓴 평가 기준 버전. */
    private String criteriaVersion;

    /** 채우지 못한 자격요건의 짧은 표시. 줄바꿈으로 나눈다. */
    @Column(nullable = false)
    private String qualificationShortfalls = "";

    private Instant analyzedAt;

    /** 평가 항목별 판정. 한 줄에 "Q-01=MET"처럼 하나씩 둔다. */
    @Column(nullable = false)
    private String criterionMarks = "";

    /** 상으로 판정한 인재상 제목. 줄바꿈으로 나눈다. */
    @Column(nullable = false)
    private String highTalents = "";

    public JobApplication(UUID recruitmentId, UUID companyId, UUID postingId, int applicationNo, String name,
            String email, String phone, String certificates) {
        this.id = UUID.randomUUID();
        this.recruitmentId = recruitmentId;
        this.companyId = companyId;
        this.postingId = postingId;
        this.applicationNo = applicationNo;
        this.name = name;
        this.email = email;
        this.phone = phone;
        this.certificates = certificates;
        this.consentPrivacy = true;
        this.consentAi = true;
        this.submittedAt = Instant.now();
        this.analysisStatus = AnalysisStatus.PENDING;
    }

    public void recordAnalysis(ApplicationAnalysis analysis) {
        this.careerYears = analysis.careerYears();
        this.lastCompany = analysis.lastCompany();
        this.documentScore = analysis.held() ? null : analysis.documentScore();
        this.documentScoreLow = analysis.documentScoreLow();
        this.scorePassed = analysis.passed();
        this.scoreHeld = analysis.held();
        this.qualificationStatus = analysis.qualificationStatus();
        this.qualificationRate = analysis.qualificationRate();
        this.qualificationScore = analysis.qualificationScore();
        this.qualificationScoreLow = analysis.qualificationScoreLow();
        this.qualificationMax = analysis.qualificationMax();
        this.preferenceScore = analysis.preferenceScore();
        this.preferenceMax = analysis.preferenceMax();
        this.criteriaVersion = analysis.criteriaVersion();
        this.qualificationShortfalls = analysis.shortfalls().stream().map(String::strip)
                .filter(text -> !text.isEmpty()).collect(Collectors.joining("\n"));
        this.criterionMarks = analysis.criterionMarks().entrySet().stream()
                .map(entry -> entry.getKey().strip() + "=" + entry.getValue().name())
                .collect(Collectors.joining("\n"));
        this.analysisStatus = AnalysisStatus.DONE;
        this.analyzedAt = Instant.now();
    }

    public List<String> shortfalls() {
        return qualificationShortfalls.isEmpty() ? List.of() : List.of(qualificationShortfalls.split("\n"));
    }

    public Map<String, CriterionMark> criterionMarks() {
        Map<String, CriterionMark> marks = new LinkedHashMap<>();
        Arrays.stream(criterionMarks.split("\n")).map(line -> line.split("=", 2)).filter(pair -> pair.length == 2)
                .forEach(pair -> marks.put(pair[0], CriterionMark.valueOf(pair[1])));
        return marks;
    }

    public List<String> highTalents() {
        return highTalents.isEmpty() ? List.of() : List.of(highTalents.split("\n"));
    }

    /** 인재상 판정 결과. 판정할 때마다 통째로 바꾼다. */
    public void recordTalents(List<String> titles) {
        this.highTalents = titles.stream().map(String::strip).filter(text -> !text.isEmpty())
                .collect(Collectors.joining("\n"));
    }

    public void markAnalysisFailed() {
        this.analysisStatus = AnalysisStatus.FAILED;
    }

    /** 실패한 분석을 다시 맡긴다. 지난 분석 결과는 새 결과가 올 때까지 그대로 둔다. */
    public void requestAnalysis() {
        this.analysisStatus = AnalysisStatus.PENDING;
    }
}
