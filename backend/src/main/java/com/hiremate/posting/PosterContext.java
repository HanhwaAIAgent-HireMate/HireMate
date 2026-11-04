package com.hiremate.posting;

import com.hiremate.company.CompanyProfile;
import com.hiremate.recruit.StageIcon;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.Map;

/** backend가 현재 기업과 채용으로 고정한 포스터 검토 자료. */
public record PosterContext(CompanyProfile company, PostingContent posting,
        @Schema(nullable = true) PosterDesign design, @Schema(nullable = true) String brandColor,
        List<PosterTurn> history, List<String> stageNames, List<String> sectionNames, boolean canvaConnected,
        Map<String, StageIcon> displayedStageIcons) {

    public PosterContext(CompanyProfile company, PostingContent posting, PosterDesign design, String brandColor,
            List<PosterTurn> history, List<String> stageNames, List<String> sectionNames, boolean canvaConnected) {
        this(company, posting, design, brandColor, history, stageNames, sectionNames, canvaConnected, Map.of());
    }

    public PosterContext(CompanyProfile company, PostingContent posting, PosterDesign design, String brandColor,
            List<PosterTurn> history, List<String> stageNames, List<String> sectionNames) {
        this(company, posting, design, brandColor, history, stageNames, sectionNames, false);
    }
}
