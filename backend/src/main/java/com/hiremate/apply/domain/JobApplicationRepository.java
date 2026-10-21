package com.hiremate.apply.domain;

import com.hiremate.apply.AnalysisStatus;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface JobApplicationRepository extends JpaRepository<JobApplication, UUID> {

    Optional<JobApplication> findByIdAndCompanyId(UUID id, UUID companyId);

    boolean existsByRecruitmentIdAndEmail(UUID recruitmentId, String email);

    Page<JobApplication> findByRecruitmentIdAndCompanyIdOrderBySubmittedAtDesc(UUID recruitmentId, UUID companyId,
            Pageable pageable);

    List<JobApplication> findByRecruitmentIdAndCompanyId(UUID recruitmentId, UUID companyId);

    List<JobApplication> findByIdInAndCompanyId(List<UUID> ids, UUID companyId);

    long countByRecruitmentIdAndCompanyId(UUID recruitmentId, UUID companyId);

    List<JobApplication> findByAnalysisStatusAndSubmittedAtBefore(AnalysisStatus status, Instant submittedBefore);

    @Query("select coalesce(max(a.applicationNo), 0) from JobApplication a where a.recruitmentId = ?1")
    int maxApplicationNo(UUID recruitmentId);
}
