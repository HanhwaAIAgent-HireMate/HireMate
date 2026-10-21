package com.hiremate.notice.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.notice.NoticeService;
import com.hiremate.notice.StageGuideView;
import com.hiremate.recruit.StageGuide;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 공고 작성 화면의 전형별 안내. 다음 전형 안내 메일에 붙는다. */
@RestController
public class StageGuideController {

    private final NoticeService notices;

    public StageGuideController(NoticeService notices) {
        this.notices = notices;
    }

    @GetMapping("/api/recruitments/{recruitmentId}/stage-guides")
    public List<StageGuideView> stageGuides(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return notices.guides(member.companyId(), recruitmentId);
    }

    @PutMapping("/api/stages/{stageId}/guide")
    public StageGuideView changeStageGuide(AuthenticatedMember member, @PathVariable UUID stageId,
            @Valid @RequestBody StageGuideRequest request) {
        return notices.changeGuide(member.companyId(), stageId,
                new StageGuide(request.schedule(), request.method(), request.place(), request.preparation(),
                        request.note()));
    }

    /** 길이는 stages 테이블의 안내 칸과 같다. note는 기타 안내다. */
    public record StageGuideRequest(@NotNull @Size(max = 200) String schedule,
            @NotNull @Size(max = 100) String method, @NotNull @Size(max = 500) String place,
            @NotNull @Size(max = 1000) String preparation, @NotNull @Size(max = 1000) String note) {
    }
}
