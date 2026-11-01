package com.hiremate.interview.domain;

import com.hiremate.interview.InterviewSessionStatus;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;

public interface InterviewSessionRepository extends JpaRepository<InterviewSession, InterviewSession.Key> {

    boolean existsByStageIdAndCompanyIdAndStatus(UUID stageId, UUID companyId, InterviewSessionStatus status);

    Optional<InterviewSession> findByStageIdAndApplicationIdAndCompanyId(UUID stageId, UUID applicationId,
            UUID companyId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from InterviewSession s where s.stageId = :stageId and s.applicationId = :applicationId "
            + "and s.companyId = :companyId")
    Optional<InterviewSession> lock(UUID companyId, UUID stageId, UUID applicationId);

    @Query("select s from InterviewSession s where s.companyId = :companyId "
            + "and (s.hrMemberId = :memberId or s.practicalMemberId = :memberId) order by s.stageId, s.applicationId")
    Page<InterviewSession> assigned(UUID companyId, UUID memberId, Pageable pageable);

    @Query("select count(s) > 0 from InterviewSession s where s.companyId = :companyId and s.stageId = :stageId "
            + "and s.applicationId = :applicationId and (s.hrMemberId = :memberId or s.practicalMemberId = :memberId)")
    boolean assignedTo(UUID companyId, UUID memberId, UUID stageId, UUID applicationId);

    @Query("select count(s) > 0 from InterviewSession s where s.companyId = :companyId "
            + "and s.applicationId = :applicationId and (s.hrMemberId = :memberId or s.practicalMemberId = :memberId)")
    boolean assignedToApplication(UUID companyId, UUID memberId, UUID applicationId);

    List<InterviewSession> findByStageIdAndCompanyId(UUID stageId, UUID companyId);
}
