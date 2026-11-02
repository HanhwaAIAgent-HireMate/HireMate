package com.hiremate.auth.api;

import com.hiremate.ai.InterviewAssistance;
import com.hiremate.auth.AuthAccess;
import com.hiremate.auth.application.InterviewMemberDirectory;
import com.hiremate.interview.InterviewAttendances;
import com.hiremate.interview.InterviewLive;
import com.hiremate.interview.InterviewSessions;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.InterviewerRole;
import com.hiremate.interview.QuestionSource;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** 배정된 면접관 전용 경로. 기업·사용자 ID와 면접 역할은 요청 본문에서 받지 않는다. */
@RestController
@RequestMapping("/api/interviewer/sessions")
public class InterviewerSessionController {

    private final AuthAccess access;
    private final InterviewSessions sessions;
    private final InterviewAssistance assistance;
    private final InterviewAttendances attendances;
    private final InterviewLive live;
    private final InterviewMemberDirectory directory;

    public InterviewerSessionController(AuthAccess access, InterviewSessions sessions, InterviewAssistance assistance,
            InterviewAttendances attendances, InterviewLive live, InterviewMemberDirectory directory) {
        this.access = access;
        this.sessions = sessions;
        this.assistance = assistance;
        this.attendances = attendances;
        this.live = live;
        this.directory = directory;
    }

    /** 면접 대기실의 [준비 완료]. 배정된 면접관이 모두 준비 완료하고 접속 중이면 면접이 바로 시작된다. */
    @PostMapping("/{stageId}/{applicationId}/ready")
    public InterviewAttendances.Attendance readyForInterview(@PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        var member = access.currentMember();
        return named(member.companyId(), sessions.ready(member.companyId(), stageId, applicationId,
                member.memberId()));
    }

    /** 시작 전에 [준비 완료]를 거둔다. */
    @DeleteMapping("/{stageId}/{applicationId}/ready")
    public InterviewAttendances.Attendance cancelInterviewReady(@PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        var member = access.currentMember();
        return named(member.companyId(), sessions.cancelReady(member.companyId(), stageId, applicationId,
                member.memberId()));
    }

    /** 면접 시간에 오지 않은 지원자를 불참으로 둔다. 같은 시간 면접의 준비 · 시작 · 종료에서 빠진다. */
    @PostMapping("/{stageId}/{applicationId}/absent")
    public InterviewSessions.InterviewerWorkspace markInterviewAbsent(@PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        var member = access.currentMember();
        return sessions.absent(member.companyId(), stageId, applicationId, member.memberId(), true);
    }

    /** 불참을 되돌린다. 같은 시간 면접이 진행 중이면 바로 함께 진행한다. */
    @DeleteMapping("/{stageId}/{applicationId}/absent")
    public InterviewSessions.InterviewerWorkspace cancelInterviewAbsent(@PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        var member = access.currentMember();
        return sessions.absent(member.companyId(), stageId, applicationId, member.memberId(), false);
    }

    /** 배정된 면접관의 준비 · 접속 현황과 전형 진행 여부. */
    @GetMapping("/{stageId}/{applicationId}/attendance")
    public InterviewAttendances.Attendance interviewAttendance(@PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        var member = access.currentMember();
        return named(member.companyId(), attendances.attendance(member.companyId(), stageId, applicationId,
                member.memberId()));
    }

    /**
     * 면접 진행 화면의 실시간 알림(SSE). 준비 · 시작 · 종료 · 질문 · 답변 · 의견이 바뀌면 changed 이벤트를 보낸다.
     * 연결이 열려 있는 동안을 접속 중으로 본다.
     */
    @GetMapping(path = "/{stageId}/{applicationId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter interviewEvents(@PathVariable UUID stageId, @PathVariable UUID applicationId) {
        var member = access.currentMember();
        attendances.requireAssigned(member.companyId(), stageId, applicationId, member.memberId());
        return live.subscribe(member.companyId(), stageId, applicationId, member.memberId());
    }

    private InterviewAttendances.Attendance named(UUID companyId, InterviewAttendances.Attendance attendance) {
        Map<UUID, String> names = directory.list(companyId).stream().collect(Collectors.toMap(
                InterviewMemberDirectory.InterviewMemberChoice::memberId,
                InterviewMemberDirectory.InterviewMemberChoice::name));
        return new InterviewAttendances.Attendance(attendance.stageActive(), attendance.attendees().stream()
                .map(attendee -> attendee.named(names.getOrDefault(attendee.memberId(), ""))).toList());
    }

    @GetMapping
    public InterviewSessions.AssignedInterviews assignedInterviews(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "30") int size) {
        var member = access.currentMember();
        return sessions.list(member.companyId(), member.memberId(), page, size);
    }

    @GetMapping("/{stageId}/{applicationId}")
    public InterviewSessions.InterviewerWorkspace interviewerWorkspace(@PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        var member = access.currentMember();
        return sessions.view(member.companyId(), stageId, applicationId, member.memberId());
    }

    @PostMapping("/{stageId}/{applicationId}/end")
    public InterviewSessions.InterviewerWorkspace endInterviewSession(@PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        var member = access.currentMember();
        return sessions.end(member.companyId(), stageId, applicationId, member.memberId());
    }

    @PutMapping("/{stageId}/{applicationId}/memo")
    public InterviewSessions.InterviewerWorkspace personalInterviewMemo(@PathVariable UUID stageId,
            @PathVariable UUID applicationId, @Valid @RequestBody PersonalInterviewMemo request) {
        var member = access.currentMember();
        return sessions.memo(member.companyId(), stageId, applicationId, member.memberId(), request.text(),
                request.expectedVersion());
    }

    @PutMapping("/{stageId}/questions/{questionId}/answer")
    public InterviewView interviewerAnswer(@PathVariable UUID stageId, @PathVariable UUID questionId,
            @Valid @RequestBody InterviewerAnswer request) {
        var member = access.currentMember();
        return sessions.answer(member.companyId(), stageId, questionId, member.memberId(), request.answer(),
                request.analyze(), request.expectedVersion(), true);
    }

    @PostMapping("/{stageId}/{applicationId}/questions")
    public InterviewView interviewerQuestion(@PathVariable UUID stageId, @PathVariable UUID applicationId,
            @Valid @RequestBody InterviewerManualQuestion request) {
        var member = access.currentMember();
        return sessions.addQuestion(member.companyId(), stageId, applicationId, member.memberId(),
                request.text(), request.interviewerRole(), true);
    }

    @PostMapping("/{stageId}/questions/{questionId}/follow-ups")
    public InterviewView interviewerFollowUp(@PathVariable UUID stageId, @PathVariable UUID questionId,
            @Valid @RequestBody InterviewerFollowUp request) {
        var member = access.currentMember();
        return sessions.followUp(member.companyId(), stageId, questionId, member.memberId(), request.text(),
                request.source(), request.check(), true);
    }

    @PostMapping("/{stageId}/questions/{questionId}/follow-ups/suggestions")
    public InterviewAssistance.InterviewerFollowUps interviewerSuggestions(@PathVariable UUID stageId,
            @PathVariable UUID questionId, @Valid @RequestBody InterviewerSuggestionsRequest request) {
        var member = access.currentMember();
        return assistance.suggest(member.companyId(), stageId, questionId, member.memberId(), request.avoid());
    }

    @DeleteMapping("/{stageId}/questions/{questionId}")
    public InterviewView deleteInterviewerQuestion(@PathVariable UUID stageId, @PathVariable UUID questionId) {
        var member = access.currentMember();
        return sessions.delete(member.companyId(), stageId, questionId, member.memberId(), true);
    }

    public record InterviewerAnswer(@NotNull @Size(max = 5000) String answer, boolean analyze,
            @NotNull @PositiveOrZero Long expectedVersion) {
    }

    public record InterviewerManualQuestion(@NotBlank @Size(max = 500) String text,
            @NotNull InterviewerRole interviewerRole) {
    }

    public record InterviewerFollowUp(@NotBlank @Size(max = 500) String text, @NotNull QuestionSource source,
            @Size(max = 300) String check) {
    }

    public record InterviewerSuggestionsRequest(@NotNull @Size(max = 4) List<@Size(max = 500) String> avoid) {
    }

    public record PersonalInterviewMemo(@NotNull @Size(max = 5000) String text,
            @Schema(description = "Workspace personalMemoVersion, not session.version")
            @NotNull @PositiveOrZero Long expectedVersion) {
    }
}
