package com.hiremate.screening.domain;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StageCandidateRepository extends JpaRepository<StageCandidate, UUID> {

    List<StageCandidate> findByStageIdAndCompanyId(UUID stageId, UUID companyId);

    List<StageCandidate> findByStageIdAndCompanyIdAndApplicationIdIn(UUID stageId, UUID companyId,
            Collection<UUID> applicationIds);

    Optional<StageCandidate> findByStageIdAndCompanyIdAndApplicationId(UUID stageId, UUID companyId,
            UUID applicationId);

    List<StageCandidate> findByRecruitmentIdAndCompanyId(UUID recruitmentId, UUID companyId);

    List<StageCandidate> findByApplicationIdAndCompanyId(UUID applicationId, UUID companyId);

    boolean existsByStageId(UUID stageId);
}
