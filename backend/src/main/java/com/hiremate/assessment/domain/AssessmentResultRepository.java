package com.hiremate.assessment.domain;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AssessmentResultRepository extends JpaRepository<AssessmentResult, UUID> {

    Optional<AssessmentResult> findByStageIdAndApplicationIdAndCompanyId(UUID stageId, UUID applicationId,
            UUID companyId);
}
