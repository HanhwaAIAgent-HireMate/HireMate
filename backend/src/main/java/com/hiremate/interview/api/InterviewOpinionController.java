package com.hiremate.interview.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.interview.CandidateOpinions;
import com.hiremate.interview.InterviewOpinions;
import com.hiremate.interview.OpinionView;
import com.hiremate.interview.Recommendation;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * 면접관 의견. 면접관 경로(/api/interviewer)는 배정된 면접관이 쓰고 읽으며, 전형 경로는 HR이 모든 의견을 본다.
 * 결정은 HR이 결정 바에서 하고, 의견은 AI에 넘기지 않는다.
 */
@RestController
public class InterviewOpinionController {

    private final InterviewOpinions opinions;

    public InterviewOpinionController(InterviewOpinions opinions) {
        this.opinions = opinions;
    }

    /** 내 의견을 저장하기 전에는 다른 면접관 의견의 내용(추천도 · 이유)이 비어 있다. */
    @GetMapping("/api/interviewer/sessions/{stageId}/{applicationId}/opinions")
    public List<OpinionView> mine(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return opinions.forInterviewer(member.companyId(), stageId, applicationId, member.memberId());
    }

    @PutMapping("/api/interviewer/sessions/{stageId}/{applicationId}/opinions/me")
    public List<OpinionView> save(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId, @Valid @RequestBody OpinionRequest request) {
        return opinions.save(member.companyId(), stageId, applicationId, member.memberId(), member.name(),
                request.recommendation(), request.comment());
    }

    @GetMapping("/api/stages/{stageId}/candidates/{applicationId}/interview/opinions")
    public List<OpinionView> candidate(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return opinions.forHr(member.companyId(), stageId, applicationId);
    }

    /** HR 지원자 목록의 의견 배지. 면접관이 배정된 지원자만 들어 있다. */
    @GetMapping("/api/stages/{stageId}/interview/opinions")
    public List<CandidateOpinions> stage(AuthenticatedMember member, @PathVariable UUID stageId) {
        return opinions.stage(member.companyId(), stageId);
    }

    /** @param comment 판단 이유. 나이 · 성별 · 출신 지역 · 혼인 여부 · 신체 조건은 쓰지 않는다 (화면이 안내한다) */
    public record OpinionRequest(@NotNull Recommendation recommendation,
            @NotBlank @Size(max = 2000) String comment) {
    }
}
