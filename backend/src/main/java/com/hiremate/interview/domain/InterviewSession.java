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

    @Column(nullable = false, columnDefinition = "text")
    private String hrMemo = "";

    @Column(nullable = false, columnDefinition = "text")
    private String practicalMemo = "";

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

    public void start() {
        status = InterviewSessionStatus.IN_PROGRESS;
        startedAt = Instant.now();
    }

    public void end() {
        status = InterviewSessionStatus.ENDED;
        endedAt = Instant.now();
    }

    public String memo(InterviewerRole role) {
        return role == InterviewerRole.HR ? hrMemo : practicalMemo;
    }

    public void memo(InterviewerRole role, String text) {
        if (role == InterviewerRole.HR) {
            hrMemo = text;
        } else {
            practicalMemo = text;
        }
    }

    public record Key(UUID stageId, UUID applicationId) implements Serializable {
        public Key() {
            this(null, null);
        }
    }
}
