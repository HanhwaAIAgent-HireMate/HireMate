package com.hiremate.assessment.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "assessment_results")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AssessmentResult {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID stageId;

    @Column(nullable = false)
    private UUID applicationId;

    @Column(nullable = false)
    private UUID companyId;

    private BigDecimal total;

    /** 영역 점수 JSON {"의사소통능력": 82, ...} */
    @Column(nullable = false)
    private String areas;

    private String grade;

    private UUID fileId;

    private String fileName;

    private String url;

    private String note;

    @Column(nullable = false, length = 20)
    private String source;

    @Column(nullable = false)
    private Instant registeredAt;

    public AssessmentResult(UUID stageId, UUID applicationId, UUID companyId) {
        this.id = UUID.randomUUID();
        this.stageId = stageId;
        this.applicationId = applicationId;
        this.companyId = companyId;
        this.areas = "{}";
        this.source = "MANUAL";
        this.registeredAt = Instant.now();
    }

    public void record(BigDecimal total, String areas, String grade, String source) {
        this.total = total;
        this.areas = areas;
        this.grade = grade;
        this.source = source;
        this.registeredAt = Instant.now();
    }

    public void submission(String url, String note) {
        this.url = url;
        this.note = note;
        this.registeredAt = Instant.now();
    }

    public void attach(UUID fileId, String fileName) {
        this.fileId = fileId;
        this.fileName = fileName;
        this.registeredAt = Instant.now();
    }
}
