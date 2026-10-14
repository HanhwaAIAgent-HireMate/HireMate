package com.hiremate.apply;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/** 지원자 카드에 필요한 지원서 전체. */
public record ApplicantDetail(ApplicantInfo info, String phone, @Schema(nullable = true) String certificates,
        List<ApplicantDocument> documents) {
}
