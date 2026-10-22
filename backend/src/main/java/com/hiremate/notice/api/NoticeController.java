package com.hiremate.notice.api;

import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.notice.NoticeGroup;
import com.hiremate.notice.NoticeService;
import com.hiremate.notice.NoticeView;
import com.hiremate.notice.OnboardingGuide;
import com.hiremate.screening.ScreeningService;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 전형 종료 3단계의 ② 합격 · 불합격 안내와 ③ 전형 종료 (STG-09, MSG-01, FIN-01). */
@RestController
@RequestMapping("/api/stages/{stageId}")
public class NoticeController {

    private final NoticeService notices;
    private final ScreeningService screening;

    public NoticeController(NoticeService notices, ScreeningService screening) {
        this.notices = notices;
        this.screening = screening;
    }

    @GetMapping("/notices")
    public List<NoticeView> notices(AuthenticatedMember member, @PathVariable UUID stageId) {
        return notices.notices(member.companyId(), stageId);
    }

    @PutMapping("/notices/{group}")
    public NoticeView edit(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable NoticeGroup group,
            @Valid @RequestBody NoticeEditRequest request) {
        return notices.edit(member.companyId(), stageId, group, request.subject(), request.greeting(),
                request.content(), request.closing());
    }

    /** 최종 합격 안내의 입사 안내. 보내기 전까지 고칠 수 있다. */
    @PutMapping("/notices/{group}/onboarding")
    public NoticeView changeOnboarding(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable NoticeGroup group, @Valid @RequestBody OnboardingRequest request) {
        return notices.changeOnboarding(member.companyId(), stageId, group, new OnboardingGuide(request.startDate(),
                request.place(), request.documents(), request.preparation(), request.note()));
    }

    /** HR이 확인한 뒤 직접 발송한다. */
    @PostMapping("/notices/{group}/send")
    public NoticeView send(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable NoticeGroup group) {
        return notices.send(member.companyId(), stageId, group, member.memberId());
    }

    /** 안내 발송까지 끝나면 전형을 종료하고 합격자로 다음 전형을 시작한다. 마지막 전형이면 채용이 끝난다. */
    @PostMapping("/finish")
    public FinishResponse finish(AuthenticatedMember member, @PathVariable UUID stageId) {
        if (!notices.allSent(member.companyId(), stageId)) {
            throw new ApiException(HttpStatus.CONFLICT, "NOTICES_NOT_SENT", "Send all notices first.");
        }
        return new FinishResponse(screening.finish(member.companyId(), stageId, member.memberId()).orElse(null));
    }

    public record NoticeEditRequest(@NotBlank @Size(max = 200) String subject,
            @NotNull @Size(max = 2000) String greeting, @NotNull @Size(max = 5000) String content,
            @NotNull @Size(max = 2000) String closing) {
    }

    /** 길이는 notices 테이블의 입사 안내 칸과 같다. note는 기타 안내다. */
    public record OnboardingRequest(@NotNull @Size(max = 200) String startDate,
            @NotNull @Size(max = 500) String place, @NotNull @Size(max = 1000) String documents,
            @NotNull @Size(max = 1000) String preparation, @NotNull @Size(max = 1000) String note) {
    }

    public record FinishResponse(@Schema(nullable = true) UUID nextStageId) {
    }
}
