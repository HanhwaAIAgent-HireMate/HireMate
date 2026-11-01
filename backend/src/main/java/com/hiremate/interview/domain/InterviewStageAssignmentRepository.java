package com.hiremate.interview.domain;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InterviewStageAssignmentRepository extends JpaRepository<InterviewStageAssignment, UUID> {

    Optional<InterviewStageAssignment> findByStageIdAndCompanyId(UUID stageId, UUID companyId);
}
