package com.hiremate.interview.domain;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InterviewScheduleRepository extends JpaRepository<InterviewSchedule, InterviewSchedule.Key> {

    List<InterviewSchedule> findByApplicationIdAndCompanyId(UUID applicationId, UUID companyId);
}
