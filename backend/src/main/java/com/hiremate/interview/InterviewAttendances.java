package com.hiremate.interview;

import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewAttendance;
import com.hiremate.interview.domain.InterviewAttendanceRepository;
import com.hiremate.interview.domain.InterviewSession;
import com.hiremate.interview.domain.InterviewSessionRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 면접관의 준비 완료. 면접은 같은 시간 면접자 묶음({@link InterviewGroups}) 단위로 연다. 배정된 면접관이 면접 진행
 * 화면에서 [준비 완료]를 누르면 그 시간 면접자 모두에 대해 준비로 세고, 이 전형의 면접 화면을 열어 둔 동안(SSE 연결)
 * 접속 중으로 본다. 배정된 면접관이 모두 준비 완료하고 접속 중이면 그 시간 면접이 함께 시작된다
 * ({@link InterviewSessions#ready}). 시작 전에 화면을 떠나면 준비 완료가 풀린다 ({@link InterviewLive}).
 */
@Service
public class InterviewAttendances {

    /** 연결이 잠깐 끊겨도(새로고침 · 재연결) 이 시간 안에 접속이 확인됐으면 접속 중으로 본다 */
    static final Duration ONLINE = Duration.ofSeconds(20);

    private final InterviewAttendanceRepository attendance;
    private final InterviewSessionRepository sessions;
    private final InterviewGroups groups;
    private final RecruitService recruits;
    private final InterviewLive live;

    public InterviewAttendances(InterviewAttendanceRepository attendance, InterviewSessionRepository sessions,
            InterviewGroups groups, RecruitService recruits, InterviewLive live) {
        this.attendance = attendance;
        this.sessions = sessions;
        this.groups = groups;
        this.recruits = recruits;
        this.live = live;
    }

    /**
     * 배정된 면접관 한 명. ended는 그 면접관이 [면접 종료]를 눌렀는지다. name은 인증 진입 계층이 채운다
     * (업무 모듈은 계정 이름을 모른다).
     */
    public record Attendee(InterviewerRole role, UUID memberId, String name, boolean ready, boolean online,
            boolean ended, boolean me) {

        public Attendee named(String name) {
            return new Attendee(role, memberId, name, ready, online, ended, me);
        }
    }

    /** 지원자 한 명이 속한 시간 면접의 준비 현황. stageActive가 false면 결과를 확정한 전형이라 의견도 읽기만 한다. */
    public record Attendance(boolean stageActive, List<Attendee> attendees) {
    }

    /** HR 화면의 진행 현황 한 줄: 지원자별 면접 일시 · 상태와 그 시간 면접의 면접관 준비 현황. */
    public record SessionProgress(UUID applicationId, InterviewSessionStatus status,
            @Schema(nullable = true) Instant scheduledAt, @Schema(nullable = true) Instant startedAt,
            @Schema(nullable = true) Instant endedAt, List<Attendee> attendees) {
    }

    /** 같은 시간 면접자 모두에 대해 준비 완료를 남긴다. 상태와 권한은 {@link InterviewSessions#ready}가 확인한다. */
    void markReady(List<InterviewSession> present, UUID memberId) {
        for (InterviewSession session : present) {
            attendance.findById(new InterviewAttendance.Key(session.getStageId(), session.getApplicationId(),
                    memberId)).ifPresentOrElse(InterviewAttendance::seen, () -> attendance.save(new InterviewAttendance(
                            session.getStageId(), session.getApplicationId(), memberId, session.getCompanyId())));
        }
        attendance.flush();
    }

    /** 같은 시간 면접자 모두에 대해 준비 완료를 거둔다. */
    void clearReady(List<InterviewSession> members, UUID memberId) {
        for (InterviewSession session : members) {
            attendance.findById(new InterviewAttendance.Key(session.getStageId(), session.getApplicationId(),
                    memberId)).ifPresent(attendance::delete);
        }
        attendance.flush();
    }

    /** 면접관이 보는 준비 현황. 배정된 면접관만 연다. */
    @Transactional(readOnly = true)
    public Attendance attendance(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        InterviewSession session = assigned(companyId, stageId, applicationId, memberId);
        boolean active = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow().status()
                == StageStatus.ACTIVE;
        return new Attendance(active, attendees(session, groups.members(session),
                attendance.findByStageIdAndCompanyId(stageId, companyId), memberId));
    }

    /** HR 화면의 전형 진행 현황: 면접관을 배정한 지원자마다. */
    @Transactional(readOnly = true)
    public List<SessionProgress> stage(UUID companyId, UUID stageId) {
        recruits.getByStage(companyId, stageId);
        List<InterviewAttendance> rows = attendance.findByStageIdAndCompanyId(stageId, companyId);
        List<InterviewSession> all = sessions.findByStageIdAndCompanyId(stageId, companyId);
        Map<UUID, Instant> at = groups.stageSchedule(companyId, stageId);
        Map<UUID, List<InterviewSession>> slots = InterviewGroups.byApplication(all, at);
        return all.stream()
                .map(session -> new SessionProgress(session.getApplicationId(), session.getStatus(),
                        at.get(session.getApplicationId()), session.getStartedAt(), session.getEndedAt(),
                        attendees(session, slots.get(session.getApplicationId()), rows, null)))
                .toList();
    }

    /** 같은 시간 면접에 배정된 면접관이 모두 준비 완료했고 지금 접속 중인가. */
    boolean ready(InterviewSession session, List<InterviewSession> members) {
        return attendees(session, members, attendance.findByStageIdAndCompanyId(session.getStageId(),
                session.getCompanyId()), null).stream().allMatch(attendee -> attendee.ready() && attendee.online());
    }

    /** 면접관의 SSE 구독 전에 배정을 확인한다. */
    @Transactional(readOnly = true)
    public void requireAssigned(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        assigned(companyId, stageId, applicationId, memberId);
    }

    /** 인사 · 실무 순서의 배정된 면접관. 준비 완료는 같은 시간 면접에서 불참을 뺀 지원자 모두에 남겼을 때다. */
    private List<Attendee> attendees(InterviewSession session, List<InterviewSession> members,
            List<InterviewAttendance> rows, UUID viewer) {
        Set<UUID> present = InterviewGroups.present(members).stream().map(InterviewSession::getApplicationId)
                .collect(Collectors.toSet());
        Instant fresh = Instant.now().minus(ONLINE);
        return List.of(
                attendee(session, members, InterviewerRole.HR, session.getHrMemberId(), present, rows, fresh, viewer),
                attendee(session, members, InterviewerRole.PRACTICAL, session.getPracticalMemberId(), present, rows,
                        fresh, viewer));
    }

    private Attendee attendee(InterviewSession session, List<InterviewSession> members, InterviewerRole role,
            UUID memberId, Set<UUID> present, List<InterviewAttendance> rows, Instant fresh, UUID viewer) {
        List<InterviewAttendance> mine = rows.stream()
                .filter(row -> row.getMemberId().equals(memberId) && present.contains(row.getApplicationId()))
                .toList();
        boolean ready = !present.isEmpty() && mine.stream().map(InterviewAttendance::getApplicationId)
                .collect(Collectors.toSet()).containsAll(present);
        boolean online = live.connected(session.getStageId(), memberId)
                || mine.stream().anyMatch(row -> row.getLastSeenAt().isAfter(fresh));
        return new Attendee(role, memberId, "", ready, online, InterviewGroups.endedBy(members, role),
                memberId.equals(viewer));
    }

    private InterviewSession assigned(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        InterviewSession session = sessions.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId,
                companyId).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "INTERVIEW_SESSION_NOT_FOUND",
                        "Interview session not found."));
        if (session.roleOf(memberId) == null) {
            throw new ApiException(HttpStatus.FORBIDDEN, "INTERVIEW_ACCESS_DENIED",
                    "Only assigned interviewers can open this interview.");
        }
        return session;
    }
}
