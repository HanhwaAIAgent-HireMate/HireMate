package com.hiremate.interview.domain;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InterviewOpinionRepository extends JpaRepository<InterviewOpinion, InterviewOpinion.Key> {

    List<InterviewOpinion> findByStageIdAndApplicationIdAndCompanyId(UUID stageId, UUID applicationId,
            UUID companyId);

    List<InterviewOpinion> findByStageIdAndCompanyId(UUID stageId, UUID companyId);
}
