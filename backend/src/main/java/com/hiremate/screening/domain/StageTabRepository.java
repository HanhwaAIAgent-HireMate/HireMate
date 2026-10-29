package com.hiremate.screening.domain;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StageTabRepository extends JpaRepository<StageTab, UUID> {

    List<StageTab> findByStageIdAndCompanyIdOrderByNumber(UUID stageId, UUID companyId);

    Optional<StageTab> findByIdAndStageIdAndCompanyId(UUID id, UUID stageId, UUID companyId);

    boolean existsByStageId(UUID stageId);
}
