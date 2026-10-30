package com.hiremate.report.domain;

import com.hiremate.report.AgentReportKind;
import com.hiremate.report.AgentReportStatus;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AgentReportRepository extends JpaRepository<AgentReport, UUID> {

    Optional<AgentReport> findByIdAndCompanyId(UUID id, UUID companyId);

    List<AgentReport> findByCompanyIdAndStageIdAndKindOrderByCreatedAtDesc(UUID companyId, UUID stageId,
            AgentReportKind kind);

    List<AgentReport> findByCompanyIdAndRecruitmentIdAndKindOrderByCreatedAtDesc(UUID companyId,
            UUID recruitmentId, AgentReportKind kind);

    List<AgentReport> findTop10ByCompanyIdAndKindAndStatusOrderByCreatedAtDesc(UUID companyId,
            AgentReportKind kind, AgentReportStatus status);
}
