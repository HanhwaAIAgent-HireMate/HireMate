package com.hiremate.apply.domain;

import com.hiremate.apply.AnalysisStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
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

    @Column(nullable = false)
    private boolean scorePassed;

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

    public void recordAnalysis(int careerYears, String lastCompany, int documentScore, boolean passed) {
        this.careerYears = careerYears;
        this.lastCompany = lastCompany;
        this.documentScore = documentScore;
        this.scorePassed = passed;
        this.analysisStatus = AnalysisStatus.DONE;
        this.analyzedAt = Instant.now();
    }

    public void markAnalysisFailed() {
        this.analysisStatus = AnalysisStatus.FAILED;
    }
}
