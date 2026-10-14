package com.hiremate.posting.domain;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JobPostingRepository extends JpaRepository<JobPosting, UUID> {

    Optional<JobPosting> findByRecruitmentIdAndCompanyId(UUID recruitmentId, UUID companyId);

    List<JobPosting> findByClosedAtIsNullAndCloseAtBefore(Instant now);
}
