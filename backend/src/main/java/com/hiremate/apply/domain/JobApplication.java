package com.hiremate.apply.domain;

import com.hiremate.apply.AnalysisStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.List;
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

    private Integer documentScore;

    /** 자격요건을 75% 이상 채웠는가. */
    @Column(nullable = false)
    private boolean scorePassed;

    /** 서류 점수를 보류했는가. 보류면 documentScore가 null이다. */
    @Column(nullable = false)
    private boolean scoreHeld;

    /** 채우지 못한 자격요건의 짧은 표시. 줄바꿈으로 나눈다. */
    @Column(nullable = false)
    private String qualificationShortfalls = "";

    private Instant analyzedAt;

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

    public void recordAnalysis(Integer careerYears, String lastCompany, Integer documentScore, boolean passed,
            boolean held, List<String> shortfalls) {
        this.careerYears = careerYears;
        this.lastCompany = lastCompany;
        this.documentScore = held ? null : documentScore;
        this.scorePassed = passed;
        this.scoreHeld = held;
        this.qualificationShortfalls = shortfalls.stream().map(String::strip).filter(text -> !text.isEmpty())
                .collect(Collectors.joining("\n"));
        this.analysisStatus = AnalysisStatus.DONE;
        this.analyzedAt = Instant.now();
    }

    public List<String> shortfalls() {
        return qualificationShortfalls.isEmpty() ? List.of() : List.of(qualificationShortfalls.split("\n"));
    }

    public void markAnalysisFailed() {
        this.analysisStatus = AnalysisStatus.FAILED;
    }

    /** 실패한 분석을 다시 맡긴다. 지난 분석 결과는 새 결과가 올 때까지 그대로 둔다. */
    public void requestAnalysis() {
        this.analysisStatus = AnalysisStatus.PENDING;
    }
}
