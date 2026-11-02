package com.hiremate.interview.domain;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InterviewSchedulingJobRepository extends JpaRepository<InterviewSchedulingJob, UUID> {

    Optional<InterviewSchedulingJob> findByPreviousStageIdAndCompanyId(UUID previousStageId, UUID companyId);
}
