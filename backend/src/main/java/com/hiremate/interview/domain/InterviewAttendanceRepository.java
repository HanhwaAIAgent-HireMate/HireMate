package com.hiremate.interview.domain;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

public interface InterviewAttendanceRepository
        extends JpaRepository<InterviewAttendance, InterviewAttendance.Key> {

    List<InterviewAttendance> findByStageIdAndApplicationIdAndCompanyId(UUID stageId, UUID applicationId,
            UUID companyId);

    List<InterviewAttendance> findByStageIdAndCompanyId(UUID stageId, UUID companyId);

    @Modifying
    @Query("update InterviewAttendance a set a.lastSeenAt = :at where a.stageId = :stageId "
            + "and a.applicationId = :applicationId and a.memberId = :memberId")
    int touch(UUID stageId, UUID applicationId, UUID memberId, Instant at);
}
