package com.hiremate.posting;

import com.hiremate.company.CompanyProfile;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/** backend가 현재 기업과 채용으로 고정한 포스터 검토 자료. */
public record PosterContext(CompanyProfile company, PostingContent posting,
        @Schema(nullable = true) PosterDesign design, @Schema(nullable = true) String brandColor,
        List<PosterTurn> history) {
}
