package com.hiremate.interview.domain;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InterviewPreparationRepository extends JpaRepository<InterviewPreparation, InterviewPreparation.Key> {

    boolean existsByStageIdAndApplicationIdAndCompanyId(UUID stageId, UUID applicationId, UUID companyId);

    void deleteByStageIdAndApplicationIdAndCompanyId(UUID stageId, UUID applicationId, UUID companyId);
}
