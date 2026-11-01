package com.hiremate.interview.domain;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InterviewAssignmentRepository extends JpaRepository<InterviewAssignment, InterviewAssignment.Key> {

    List<InterviewAssignment> findByStageIdAndCompanyId(UUID stageId, UUID companyId);

    List<InterviewAssignment> findByMemberIdAndCompanyId(UUID memberId, UUID companyId);

    List<InterviewAssignment> findByMemberIdAndStageIdAndCompanyId(UUID memberId, UUID stageId, UUID companyId);

    void deleteByStageIdAndCompanyId(UUID stageId, UUID companyId);
}
