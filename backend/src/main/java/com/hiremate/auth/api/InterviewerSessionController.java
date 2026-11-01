package com.hiremate.auth.api;

import com.hiremate.ai.InterviewAssistance;
import com.hiremate.auth.AuthAccess;
import com.hiremate.interview.InterviewSessions;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.InterviewerRole;
import com.hiremate.interview.QuestionSource;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 배정된 면접관 전용 경로. 기업·사용자 ID와 면접 역할은 요청 본문에서 받지 않는다. */
@RestController
@RequestMapping("/api/interviewer/sessions")
public class InterviewerSessionController {

    private final AuthAccess access;
    private final InterviewSessions sessions;
    private final InterviewAssistance assistance;

    public InterviewerSessionController(AuthAccess access, InterviewSessions sessions, InterviewAssistance assistance) {
        this.access = access;
        this.sessions = sessions;
        this.assistance = assistance;
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

    @PostMapping("/{stageId}/{applicationId}/start")
    public InterviewSessions.InterviewerWorkspace startInterviewSession(@PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        var member = access.currentMember();
        return sessions.start(member.companyId(), stageId, applicationId, member.memberId());
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
            @NotNull @PositiveOrZero Long expectedVersion) {
    }
}
