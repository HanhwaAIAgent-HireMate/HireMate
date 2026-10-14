package com.hiremate.report.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "reports")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Report {

    @Id
    private UUID id;

    @Column(nullable = false, unique = true)
    private UUID recruitmentId;

    @Column(nullable = false)
    private UUID companyId;

    /** ReportContent JSON */
    @Column(nullable = false)
    private String content;

    @Column(nullable = false, length = 50)
    private String agent;

    @Column(nullable = false)
    private Instant generatedAt;

    public Report(UUID recruitmentId, UUID companyId, String content, String agent) {
        this.id = UUID.randomUUID();
        this.recruitmentId = recruitmentId;
        this.companyId = companyId;
        this.content = content;
        this.agent = agent;
        this.generatedAt = Instant.now();
    }
}
