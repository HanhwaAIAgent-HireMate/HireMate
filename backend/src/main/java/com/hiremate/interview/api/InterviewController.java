package com.hiremate.interview.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.InterviewerRole;
import com.hiremate.interview.QuestionSource;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 면접 맞춤 질문 · 답변 기록 (STG-12, STG-13). */
@RestController
@RequestMapping("/api/stages/{stageId}")
public class InterviewController {

    private final InterviewService interviews;

    public InterviewController(InterviewService interviews) {
        this.interviews = interviews;
    }

    @GetMapping("/candidates/{applicationId}/interview")
    public InterviewView view(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return interviews.view(member.companyId(), stageId, applicationId);
    }

    /** 면접관이 필요한 질문을 직접 추가한다. */
    @PostMapping("/candidates/{applicationId}/interview/questions")
    public InterviewView addQuestion(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId, @Valid @RequestBody QuestionRequest request) {
        return interviews.addManualQuestion(member.companyId(), stageId, applicationId, request.text(),
                request.interviewerRole());
    }

    @PutMapping("/candidates/{applicationId}/interview/schedule")
    public InterviewView schedule(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId, @Valid @RequestBody ScheduleRequest request) {
        return interviews.schedule(member.companyId(), stageId, applicationId, request.scheduledAt(),
                request.interviewers());
    }

    /** 질문별 답변 기록. */
    @PutMapping("/interview/questions/{questionId}/answer")
    public InterviewView answer(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID questionId, @Valid @RequestBody AnswerRequest request) {
        return interviews.answer(member.companyId(), stageId, questionId, request.answer(),
                request.analyze() == null || request.analyze());
    }

    /** 🎤 면접관이 고른(또는 직접 쓴) 꼬리질문을 원래 질문 아래에 넣는다. 최대 2단계, 질문마다 하나. */
    @PostMapping("/interview/questions/{questionId}/follow-ups")
    public InterviewView addFollowUp(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID questionId, @Valid @RequestBody FollowUpRequest request) {
        return interviews.addFollowUp(member.companyId(), stageId, questionId, request.text(), request.source(),
                request.check());
    }

    @PutMapping("/interview/questions/{questionId}/role")
    public InterviewView assignRole(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID questionId, @Valid @RequestBody RoleRequest request) {
        return interviews.assignRole(member.companyId(), stageId, questionId, request.interviewerRole());
    }

    public record RoleRequest(@Schema(nullable = true) InterviewerRole interviewerRole) {
    }

    @DeleteMapping("/interview/questions/{questionId}")
    public InterviewView delete(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID questionId) {
        return interviews.deleteQuestion(member.companyId(), stageId, questionId);
    }

    public record QuestionRequest(@NotBlank @Size(max = 500) String text,
            @Schema(nullable = true) InterviewerRole interviewerRole) {
    }

    /**
     * @param analyze 💾 false면 자동 저장(DB에만 저장, 분석 없음). 면접관이 답변 칸을 떠날 때 true로 보내 분석을 요청한다.
     *                없으면 true (예전 화면과 같다)
     */
    public record AnswerRequest(@NotNull @Size(max = 5000) String answer,
            @Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED, nullable = true) Boolean analyze) {
    }

    /**
     * @param source AI 제안을 골랐으면 AI, 직접 썼으면 MANUAL
     * @param check AI 제안의 확인 포인트. 직접 썼으면 null
     */
    public record FollowUpRequest(@NotBlank @Size(max = 500) String text, @NotNull QuestionSource source,
            @Schema(nullable = true) @Size(max = 300) String check) {
    }

    public record ScheduleRequest(@Schema(nullable = true) Instant scheduledAt,
            @NotNull @Size(max = 200) String interviewers) {
    }
}
