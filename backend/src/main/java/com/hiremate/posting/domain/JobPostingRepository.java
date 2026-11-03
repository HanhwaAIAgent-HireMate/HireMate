package com.hiremate.posting.domain;

import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;

public interface JobPostingRepository extends JpaRepository<JobPosting, UUID> {

    Optional<JobPosting> findByRecruitmentIdAndCompanyId(UUID recruitmentId, UUID companyId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from JobPosting p where p.recruitmentId = :recruitmentId and p.companyId = :companyId")
    Optional<JobPosting> lockPosting(UUID recruitmentId, UUID companyId);

    List<JobPosting> findByClosedAtIsNullAndCloseAtBefore(Instant now);
}
