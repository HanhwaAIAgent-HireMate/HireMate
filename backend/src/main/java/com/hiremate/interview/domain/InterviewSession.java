package com.hiremate.interview.domain;

import com.hiremate.interview.InterviewSessionStatus;
import com.hiremate.interview.InterviewerRole;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "interview_sessions")
@IdClass(InterviewSession.Key.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewSession {

    @Id
    private UUID stageId;

    @Id
    private UUID applicationId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private UUID hrMemberId;

    @Column(nullable = false)
    private UUID practicalMemberId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private InterviewSessionStatus status = InterviewSessionStatus.SCHEDULED;

    private Instant startedAt;
    private Instant endedAt;

    /** 면접관마다 [면접 종료]를 누른 때. 두 면접관이 모두 누르면 면접이 끝난다 */
    private Instant hrEndedAt;
    private Instant practicalEndedAt;

    @Column(nullable = false, columnDefinition = "text")
    private String hrMemo = "";

    @Column(nullable = false, columnDefinition = "text")
    private String practicalMemo = "";

    @Column(nullable = false)
    private long hrMemoVersion;

    @Column(nullable = false)
    private long practicalMemoVersion;

    @Version
    private long version;

    public InterviewSession(UUID companyId, UUID stageId, UUID applicationId, UUID hrMemberId, UUID practicalMemberId) {
        this.companyId = companyId;
        this.stageId = stageId;
        this.applicationId = applicationId;
        assign(hrMemberId, practicalMemberId);
    }

    public void assign(UUID hrMemberId, UUID practicalMemberId) {
        this.hrMemberId = hrMemberId;
        this.practicalMemberId = practicalMemberId;
    }

    public InterviewerRole roleOf(UUID memberId) {
        if (hrMemberId.equals(memberId)) {
            return InterviewerRole.HR;
        }
        return practicalMemberId.equals(memberId) ? InterviewerRole.PRACTICAL : null;
    }

    /** 같은 시간 면접은 한꺼번에 시작하므로 시작 시각을 함께 받는다 */
    public void start(Instant at) {
        status = InterviewSessionStatus.IN_PROGRESS;
        startedAt = at;
    }

    /** 면접 시간에 오지 않았다 */
    public void markAbsent() {
        status = InterviewSessionStatus.ABSENT;
    }

    /** 불참을 거두고 같은 시간 면접의 상태로 되돌린다 */
    public void rejoin(InterviewSessionStatus groupStatus, Instant groupStartedAt) {
        status = groupStatus;
        startedAt = groupStatus == InterviewSessionStatus.IN_PROGRESS ? groupStartedAt : null;
        endedAt = null;
        hrEndedAt = null;
        practicalEndedAt = null;
    }

    /** 면접관 한 명이 이 지원자의 면접을 마쳤다 */
    public void endBy(InterviewerRole role, Instant at) {
        if (role == InterviewerRole.HR) {
            hrEndedAt = at;
        } else {
            practicalEndedAt = at;
        }
    }

    /** 이 담당 면접관이 면접을 마쳤나. 면접이 끝났으면 모두 마친 것이다 */
    public boolean endedBy(InterviewerRole role) {
        return status == InterviewSessionStatus.ENDED
                || (role == InterviewerRole.HR ? hrEndedAt : practicalEndedAt) != null;
    }

    public void end(Instant at) {
        status = InterviewSessionStatus.ENDED;
        endedAt = at;
    }

    public String memo(InterviewerRole role) {
        return role == InterviewerRole.HR ? hrMemo : practicalMemo;
    }

    public void memo(InterviewerRole role, String text) {
        if (role == InterviewerRole.HR) {
            hrMemo = text;
            hrMemoVersion++;
        } else {
            practicalMemo = text;
            practicalMemoVersion++;
        }
    }

    public long memoVersion(InterviewerRole role) {
        return role == InterviewerRole.HR ? hrMemoVersion : practicalMemoVersion;
    }

    public record Key(UUID stageId, UUID applicationId) implements Serializable {
        public Key() {
            this(null, null);
        }
    }
}
