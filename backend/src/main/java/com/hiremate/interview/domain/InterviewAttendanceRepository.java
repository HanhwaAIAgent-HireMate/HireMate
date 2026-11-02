package com.hiremate.interview.domain;

import com.hiremate.interview.InterviewSessionStatus;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.transaction.annotation.Transactional;

public interface InterviewAttendanceRepository
        extends JpaRepository<InterviewAttendance, InterviewAttendance.Key> {

    List<InterviewAttendance> findByStageIdAndApplicationIdAndCompanyId(UUID stageId, UUID applicationId,
            UUID companyId);

    List<InterviewAttendance> findByStageIdAndCompanyId(UUID stageId, UUID companyId);

    @Modifying
    @Query("update InterviewAttendance a set a.lastSeenAt = :at where a.stageId = :stageId "
            + "and a.applicationId = :applicationId and a.memberId = :memberId")
    int touch(UUID stageId, UUID applicationId, UUID memberId, Instant at);

    /** 이 상태인 면접에 남은 면접관의 준비 완료를 거둔다. 시작 전에 화면을 떠난 면접관에게 쓴다. */
    @Transactional
    @Modifying
    @Query("delete from InterviewAttendance a where a.stageId = :stageId and a.applicationId = :applicationId "
            + "and a.memberId = :memberId and exists (select s.applicationId from InterviewSession s "
            + "where s.stageId = a.stageId and s.applicationId = a.applicationId and s.status = :status)")
    int release(UUID stageId, UUID applicationId, UUID memberId, InterviewSessionStatus status);
}
