package com.hiremate.auth.api;

import com.hiremate.auth.AuthAccess;
import com.hiremate.auth.MemberPrincipal;
import com.hiremate.auth.application.InterviewMemberDirectory;
import com.hiremate.interview.InterviewAssignments;
import com.hiremate.interview.InterviewAttendances;
import com.hiremate.interview.InterviewLive;
import com.hiremate.interview.InterviewSessions;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** HR의 면접관 배정. 인증 진입 계층에서 계정 소속을 검증하고 업무 모듈에 ID만 전달한다. */
@RestController
public class InterviewAssignmentController {

    private final AuthAccess access;
    private final InterviewMemberDirectory directory;
    private final InterviewSessions sessions;
    private final InterviewAssignments assignments;
    private final InterviewAttendances attendances;
    private final InterviewLive live;

    public InterviewAssignmentController(AuthAccess access, InterviewMemberDirectory directory,
            InterviewSessions sessions, InterviewAttendances attendances, InterviewLive live,
            InterviewAssignments assignments) {
        this.access = access;
        this.directory = directory;
        this.sessions = sessions;
        this.assignments = assignments;
        this.attendances = attendances;
        this.live = live;
    }

    /** HR 화면의 면접 진행 현황: 면접관을 배정한 지원자마다 면접 상태와 면접관 입장 · 접속 현황. */
    @GetMapping("/api/stages/{stageId}/interview/sessions")
    public List<InterviewAttendances.SessionProgress> interviewProgress(@PathVariable UUID stageId) {
        access.requireHr();
        UUID companyId = access.currentMember().companyId();
        Map<UUID, String> names = directory.list(companyId).stream().collect(Collectors.toMap(
                InterviewMemberDirectory.InterviewMemberChoice::memberId,
                InterviewMemberDirectory.InterviewMemberChoice::name));
        return attendances.stage(companyId, stageId).stream()
                .map(row -> new InterviewAttendances.SessionProgress(row.applicationId(), row.status(),
                        row.startedAt(), row.endedAt(), row.attendees().stream()
                                .map(attendee -> attendee.named(names.getOrDefault(attendee.memberId(), "")))
                                .toList()))
                .toList();
    }

    /** HR 화면의 실시간 알림(SSE): 전형의 어느 면접이든 바뀌면 changed 이벤트를 보낸다. */
    @GetMapping(path = "/api/stages/{stageId}/interview/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter interviewEvents(@PathVariable UUID stageId) {
        access.requireHr();
        attendances.stage(access.currentMember().companyId(), stageId);
        return live.subscribeStage(stageId);
    }

    @GetMapping("/api/companies/current/interview-members")
    public List<InterviewMemberDirectory.InterviewMemberChoice> interviewMembers() {
        access.requireHr();
        return directory.list(access.currentMember().companyId());
    }

    @GetMapping("/api/stages/{stageId}/candidates/{applicationId}/interview/session")
    public InterviewSessions.InterviewAssignment interviewAssignment(@PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        access.requireHr();
        return sessions.assignment(access.currentMember().companyId(), stageId, applicationId);
    }

    @GetMapping("/api/stages/{stageId}/interview/assignment")
    public InterviewAssignments.StageInterviewAssignment stageAssignment(@PathVariable UUID stageId) {
        access.requireHr();
        return assignments.view(access.currentMember().companyId(), stageId);
    }

    @PutMapping("/api/stages/{stageId}/interview/assignment")
    public InterviewAssignments.StageInterviewAssignment assignInterviewers(@PathVariable UUID stageId,
            @Valid @RequestBody InterviewAssignmentRequest request) {
        access.requireHr();
        MemberPrincipal member = access.currentMember();
        directory.requireMember(member.companyId(), request.hrMemberId());
        directory.requireMember(member.companyId(), request.practicalMemberId());
        return assignments.assign(member.companyId(), stageId, request.hrMemberId(),
                request.practicalMemberId(), request.expectedVersion());
    }

    public record InterviewAssignmentRequest(@NotNull UUID hrMemberId, @NotNull UUID practicalMemberId,
            @Schema(nullable = true) Long expectedVersion) {
    }
}
