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
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 면접관 입장. 배정된 면접관이 면접 진행 화면에서 [면접 입장]을 누르면 입장으로 세고, 화면을 열어 둔 동안(SSE 연결)
 * 접속 중으로 본다. 배정된 면접관이 모두 입장하고 접속 중이어야 면접을 시작한다 ({@link InterviewSessions#start}).
 */
@Service
public class InterviewAttendances {

    /** 연결이 잠깐 끊겨도(새로고침 · 재연결) 이 시간 안에 접속이 확인됐으면 접속 중으로 본다 */
    static final Duration ONLINE = Duration.ofSeconds(20);

    private final InterviewAttendanceRepository attendance;
    private final InterviewSessionRepository sessions;
    private final RecruitService recruits;
    private final InterviewLive live;
    private final ApplicationEventPublisher events;

    public InterviewAttendances(InterviewAttendanceRepository attendance, InterviewSessionRepository sessions,
            RecruitService recruits, InterviewLive live, ApplicationEventPublisher events) {
        this.attendance = attendance;
        this.sessions = sessions;
        this.recruits = recruits;
        this.live = live;
        this.events = events;
    }

    /** 배정된 면접관 한 명. name은 인증 진입 계층이 채운다 (업무 모듈은 계정 이름을 모른다). */
    public record Attendee(InterviewerRole role, UUID memberId, String name, boolean entered, boolean online,
            boolean me) {

        public Attendee named(String name) {
            return new Attendee(role, memberId, name, entered, online, me);
        }
    }

    /** 지원자 한 명의 입장 현황. stageActive가 false면 결과를 확정한 전형이라 의견도 읽기만 한다. */
    public record Attendance(boolean stageActive, List<Attendee> attendees) {
    }

    /** HR 화면의 진행 현황 한 줄: 지원자별 면접 상태와 면접관 입장 현황. */
    public record SessionProgress(UUID applicationId, InterviewSessionStatus status,
            @Schema(nullable = true) Instant startedAt, @Schema(nullable = true) Instant endedAt,
            List<Attendee> attendees) {
    }

    @Transactional
    public Attendance enter(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        InterviewSession session = assigned(companyId, stageId, applicationId, memberId);
        if (recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow().status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "The interview stage is not active.");
        }
        attendance.findById(new InterviewAttendance.Key(stageId, applicationId, memberId)).ifPresentOrElse(
                InterviewAttendance::seen,
                () -> attendance.save(new InterviewAttendance(stageId, applicationId, memberId, companyId)));
        events.publishEvent(new InterviewSessionChanged(companyId, stageId, applicationId));
        return view(companyId, session, memberId);
    }

    /** 면접관이 보는 입장 현황. 배정된 면접관만 연다. */
    @Transactional(readOnly = true)
    public Attendance attendance(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        return view(companyId, assigned(companyId, stageId, applicationId, memberId), memberId);
    }

    /** HR 화면의 전형 진행 현황: 면접관을 배정한 지원자마다. */
    @Transactional(readOnly = true)
    public List<SessionProgress> stage(UUID companyId, UUID stageId) {
        recruits.getByStage(companyId, stageId);
        Map<UUID, List<InterviewAttendance>> entered = attendance.findByStageIdAndCompanyId(stageId, companyId)
                .stream().collect(Collectors.groupingBy(InterviewAttendance::getApplicationId));
        return sessions.findByStageIdAndCompanyId(stageId, companyId).stream()
                .map(session -> new SessionProgress(session.getApplicationId(), session.getStatus(),
                        session.getStartedAt(), session.getEndedAt(),
                        attendees(session, entered.getOrDefault(session.getApplicationId(), List.of()), null)))
                .toList();
    }

    /** 배정된 면접관이 모두 입장했고 지금 접속 중인가. */
    boolean ready(InterviewSession session) {
        return attendees(session, attendance.findByStageIdAndApplicationIdAndCompanyId(session.getStageId(),
                session.getApplicationId(), session.getCompanyId()), null).stream()
                .allMatch(attendee -> attendee.entered() && attendee.online());
    }

    /** 면접관의 SSE 구독 전에 배정을 확인한다. */
    @Transactional(readOnly = true)
    public void requireAssigned(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        assigned(companyId, stageId, applicationId, memberId);
    }

    private Attendance view(UUID companyId, InterviewSession session, UUID viewer) {
        boolean active = recruits.getByStage(companyId, session.getStageId()).stage(session.getStageId())
                .orElseThrow().status() == StageStatus.ACTIVE;
        return new Attendance(active, attendees(session, attendance.findByStageIdAndApplicationIdAndCompanyId(
                session.getStageId(), session.getApplicationId(), companyId), viewer));
    }

    /** 인사 · 실무 순서의 배정된 면접관. */
    private List<Attendee> attendees(InterviewSession session, List<InterviewAttendance> found, UUID viewer) {
        Map<UUID, InterviewAttendance> byMember = found.stream()
                .collect(Collectors.toMap(InterviewAttendance::getMemberId, Function.identity()));
        Instant fresh = Instant.now().minus(ONLINE);
        return List.of(
                attendee(session, InterviewerRole.HR, session.getHrMemberId(), byMember, fresh, viewer),
                attendee(session, InterviewerRole.PRACTICAL, session.getPracticalMemberId(), byMember, fresh, viewer));
    }

    private Attendee attendee(InterviewSession session, InterviewerRole role, UUID memberId,
            Map<UUID, InterviewAttendance> byMember, Instant fresh, UUID viewer) {
        InterviewAttendance entered = byMember.get(memberId);
        boolean online = live.connected(session.getStageId(), session.getApplicationId(), memberId)
                || entered != null && entered.getLastSeenAt().isAfter(fresh);
        return new Attendee(role, memberId, "", entered != null, online, memberId.equals(viewer));
    }

    private InterviewSession assigned(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        InterviewSession session = sessions.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId,
                companyId).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "INTERVIEW_SESSION_NOT_FOUND",
                        "Interview session not found."));
        if (session.roleOf(memberId) == null) {
            throw new ApiException(HttpStatus.FORBIDDEN, "INTERVIEW_ACCESS_DENIED",
                    "Only assigned interviewers can enter.");
        }
        return session;
    }
}
