package com.hiremate.report.domain;

import com.hiremate.report.AgentReportKind;
import com.hiremate.report.AgentReportStatus;
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

/** Report Agent 리포트 한 건. 묶음(bundle)과 결과(result)는 JSON으로 그대로 남긴다. */
@Entity
@Table(name = "agent_reports")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AgentReport {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private UUID recruitmentId;

    @Column(nullable = false)
    private UUID stageId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private AgentReportKind kind;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private AgentReportStatus status;

    private UUID requestedBy;

    @Column(nullable = false, length = 100)
    private String focus;

    @Column(nullable = false)
    private boolean brief;

    @Column(nullable = false)
    private String bundle;

    private String result;

    @Column(length = 500)
    private String error;

    @Column(nullable = false)
    private Instant createdAt;

    private Instant finishedAt;

    public AgentReport(UUID companyId, UUID recruitmentId, UUID stageId, AgentReportKind kind, UUID requestedBy,
            String focus, boolean brief, String bundle) {
        this.id = UUID.randomUUID();
        this.companyId = companyId;
        this.recruitmentId = recruitmentId;
        this.stageId = stageId;
        this.kind = kind;
        this.status = AgentReportStatus.PENDING;
        this.requestedBy = requestedBy;
        this.focus = focus;
        this.brief = brief;
        this.bundle = bundle;
        this.createdAt = Instant.now();
    }

    public void complete(String result, String bundle) {
        this.status = AgentReportStatus.DONE;
        this.result = result;
        if (bundle != null) {
            this.bundle = bundle;
        }
        this.error = null;
        this.finishedAt = Instant.now();
    }

    public void fail(String error) {
        this.status = AgentReportStatus.FAILED;
        this.error = error == null ? null : error.substring(0, Math.min(error.length(), 500));
        this.finishedAt = Instant.now();
    }
}
