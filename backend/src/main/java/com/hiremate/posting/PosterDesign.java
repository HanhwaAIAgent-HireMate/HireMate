package com.hiremate.posting;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.util.UUID;

/** 웹 포스터와 PDF 출력이 공유하는 디자인. 내용은 공고 본문을 그대로 사용한다. */
public record PosterDesign(@NotNull Template template, @NotNull Mood mood,
        @NotNull @Pattern(regexp = "^#[0-9a-fA-F]{6}$") String color,
        @Min(0) @Max(2) int decoration, boolean enabled, boolean showLogo,
        @Schema(nullable = true) UUID logoFileId, BackgroundStyle backgroundStyle) {

    public PosterDesign {
        backgroundStyle = backgroundStyle == null ? BackgroundStyle.SOLID : backgroundStyle;
    }

    public PosterDesign(Template template, Mood mood, String color, int decoration, boolean enabled,
            boolean showLogo, UUID logoFileId) {
        this(template, mood, color, decoration, enabled, showLogo, logoFileId, BackgroundStyle.SOLID);
    }

    public enum BackgroundStyle {
        SOLID, SOFT_GRADIENT
    }

    public enum Template {
        CLASSIC, EDITORIAL, BOLD, PREMIUM, NATURAL, TICKET
    }

    public enum Mood {
        TRUST, CLEAR, WARM, PREMIUM, LIVELY, NATURAL
    }
}
