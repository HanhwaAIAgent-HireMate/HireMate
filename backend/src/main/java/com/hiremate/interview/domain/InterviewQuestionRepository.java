package com.hiremate.interview.domain;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InterviewQuestionRepository extends JpaRepository<InterviewQuestion, UUID> {

    List<InterviewQuestion> findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(UUID stageId, UUID applicationId,
            UUID companyId);

    List<InterviewQuestion> findByApplicationIdAndCompanyIdOrderBySeq(UUID applicationId, UUID companyId);

    Optional<InterviewQuestion> findByIdAndStageIdAndCompanyId(UUID id, UUID stageId, UUID companyId);
}
