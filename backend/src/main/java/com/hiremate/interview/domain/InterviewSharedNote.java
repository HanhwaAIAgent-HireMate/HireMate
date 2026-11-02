package com.hiremate.interview.domain;

import com.hiremate.interview.InterviewerRole;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 개인 메모와 분리한 면접 공유 기록. 작성 계정만 수정하며 AI에 전달하지 않는다. */
@Entity
@Table(name = "interview_shared_notes")
@IdClass(InterviewSharedNote.Key.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewSharedNote {
    @Id
    private UUID stageId;
    @Id
    private UUID applicationId;
    @Id
    private UUID memberId;
    @Column(nullable = false)
    private UUID companyId;
    @Column(nullable = false, length = 100)
    private String memberName;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private InterviewerRole interviewerRole;
    @Column(nullable = false, columnDefinition = "text")
    private String text = "";
    @Column(nullable = false)
    private long version;
    @Column(nullable = false)
    private Instant updatedAt;

    public InterviewSharedNote(UUID stageId, UUID applicationId, UUID memberId, UUID companyId) {
        this.stageId = stageId;
        this.applicationId = applicationId;
        this.memberId = memberId;
        this.companyId = companyId;
    }

    public void write(String name, InterviewerRole role, String text) {
        this.memberName = name;
        this.interviewerRole = role;
        this.text = text;
        this.version++;
        this.updatedAt = Instant.now();
    }

    public record Key(UUID stageId, UUID applicationId, UUID memberId) implements Serializable {
        public Key() {
            this(null, null, null);
        }
    }
}
