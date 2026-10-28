package com.hiremate.company;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.UUID;

/** 기업 공통 포스터 기본 디자인과 로고. 새 공고에 복사하고 기존 공고는 바꾸지 않는다. */
public record PosterBrand(String template, String mood, String color, int decoration,
        @Schema(nullable = true) UUID logoFileId, List<PosterTemplate> templates) {

    public static final PosterBrand DEFAULT = new PosterBrand("CLASSIC", "TRUST", "#2459a6", 1, null, List.of());

    public PosterBrand {
        templates = templates == null ? List.of() : List.copyOf(templates);
    }
}
