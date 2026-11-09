package com.hiremate.apply.domain;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.CriterionMark;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
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

    private UUID photoFileId;

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

    /** 중으로 판정한 인재상 제목. 줄바꿈으로 나눈다. */
    @Column(nullable = false)
    private String midTalents = "";

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

    public void setPhotoFileId(UUID photoFileId) {
        this.photoFileId = photoFileId;
    }

    public void recordAnalysis(ApplicationAnalysis analysis) {
        this.careerYears = analysis.careerYears();
        this.lastCompany = analysis.lastCompany();
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

    public List<String> midTalents() {
        return midTalents.isEmpty() ? List.of() : List.of(midTalents.split("\n"));
    }

    /** 인재상 판정 결과. 판정할 때마다 통째로 바꾼다. */
    public void recordTalents(List<String> high, List<String> mid) {
        this.highTalents = lines(high);
        this.midTalents = lines(mid);
    }

    private static String lines(List<String> titles) {
        return titles.stream().map(String::strip).filter(text -> !text.isEmpty()).collect(Collectors.joining("\n"));
    }

    public void markAnalysisFailed() {
        this.analysisStatus = AnalysisStatus.FAILED;
    }

    /** 실패한 분석을 다시 맡긴다. 지난 분석 결과는 새 결과가 올 때까지 그대로 둔다. */
    public void requestAnalysis() {
        this.analysisStatus = AnalysisStatus.PENDING;
    }
}
