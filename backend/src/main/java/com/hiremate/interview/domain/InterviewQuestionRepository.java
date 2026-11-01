package com.hiremate.interview.domain;

import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;

public interface InterviewQuestionRepository extends JpaRepository<InterviewQuestion, UUID> {

    List<InterviewQuestion> findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(UUID stageId, UUID applicationId,
            UUID companyId);

    List<InterviewQuestion> findByApplicationIdAndCompanyIdOrderBySeq(UUID applicationId, UUID companyId);

    Optional<InterviewQuestion> findByIdAndStageIdAndCompanyId(UUID id, UUID stageId, UUID companyId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select q from InterviewQuestion q where q.id = :questionId and q.stageId = :stageId "
            + "and q.companyId = :companyId")
    Optional<InterviewQuestion> lock(UUID companyId, UUID stageId, UUID questionId);
}
