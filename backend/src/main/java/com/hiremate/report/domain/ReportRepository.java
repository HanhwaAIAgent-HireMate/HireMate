package com.hiremate.report.domain;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ReportRepository extends JpaRepository<Report, UUID> {

    Optional<Report> findByRecruitmentIdAndCompanyId(UUID recruitmentId, UUID companyId);

    boolean existsByRecruitmentId(UUID recruitmentId);
}
