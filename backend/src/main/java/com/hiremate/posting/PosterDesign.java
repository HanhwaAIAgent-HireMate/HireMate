package com.hiremate.posting;

import com.hiremate.recruit.StageIcon;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** 웹 포스터와 PDF 출력이 공유하는 디자인. 내용은 공고 본문을 그대로 사용한다. */
public record PosterDesign(@NotNull Template template, @NotNull Mood mood,
        @NotNull @Pattern(regexp = "^#[0-9a-fA-F]{6}$") String color,
        @Min(0) @Max(2) int decoration, boolean enabled, boolean showLogo,
        @Schema(nullable = true) UUID logoFileId, BackgroundStyle backgroundStyle,
        @Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED)
        @Size(max = 10) Map<@Size(min = 1, max = 50) String, @NotNull StageIcon> stageIcons,
        @Size(max = 12) List<@NotNull @Min(1) @Max(12) Integer> readableSections,
        @Schema(nullable = true) @Size(max = 200000) String canvasJson,
        @Schema(nullable = true, requiredMode = Schema.RequiredMode.NOT_REQUIRED) @Size(max = 60) String tagline,
        @Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED) Motion motion) {

    public PosterDesign {
        backgroundStyle = backgroundStyle == null ? BackgroundStyle.SOLID : backgroundStyle;
        stageIcons = stageIcons == null ? Map.of() : Map.copyOf(stageIcons);
        readableSections = readableSections == null ? List.of() : List.copyOf(readableSections);
        motion = motion == null ? Motion.NONE : motion;
    }

    public PosterDesign(Template template, Mood mood, String color, int decoration, boolean enabled,
            boolean showLogo, UUID logoFileId, BackgroundStyle backgroundStyle, Map<String, StageIcon> stageIcons,
            List<Integer> readableSections, String canvasJson, String tagline) {
        this(template, mood, color, decoration, enabled, showLogo, logoFileId, backgroundStyle, stageIcons,
                readableSections, canvasJson, tagline, Motion.NONE);
    }

    public PosterDesign(Template template, Mood mood, String color, int decoration, boolean enabled,
            boolean showLogo, UUID logoFileId, BackgroundStyle backgroundStyle, Map<String, StageIcon> stageIcons,
            List<Integer> readableSections, String canvasJson) {
        this(template, mood, color, decoration, enabled, showLogo, logoFileId, backgroundStyle, stageIcons,
                readableSections, canvasJson, null);
    }

    public PosterDesign(Template template, Mood mood, String color, int decoration, boolean enabled,
            boolean showLogo, UUID logoFileId, BackgroundStyle backgroundStyle, Map<String, StageIcon> stageIcons,
            List<Integer> readableSections) {
        this(template, mood, color, decoration, enabled, showLogo, logoFileId, backgroundStyle, stageIcons,
                readableSections, null);
    }

    public PosterDesign(Template template, Mood mood, String color, int decoration, boolean enabled,
            boolean showLogo, UUID logoFileId, BackgroundStyle backgroundStyle, Map<String, StageIcon> stageIcons) {
        this(template, mood, color, decoration, enabled, showLogo, logoFileId, backgroundStyle, stageIcons, List.of());
    }

    public PosterDesign(Template template, Mood mood, String color, int decoration, boolean enabled,
            boolean showLogo, UUID logoFileId, BackgroundStyle backgroundStyle) {
        this(template, mood, color, decoration, enabled, showLogo, logoFileId, backgroundStyle, Map.of());
    }

    public PosterDesign(Template template, Mood mood, String color, int decoration, boolean enabled,
            boolean showLogo, UUID logoFileId) {
        this(template, mood, color, decoration, enabled, showLogo, logoFileId, BackgroundStyle.SOLID);
    }

    public enum BackgroundStyle {
        SOLID, SOFT_GRADIENT
    }

    public enum Motion {
        NONE, WAVE, GLOW
    }

    public enum Template {
        CLASSIC, EDITORIAL, BOLD, PREMIUM, NATURAL, TICKET
    }

    public enum Mood {
        TRUST, CLEAR, WARM, PREMIUM, LIVELY, NATURAL
    }
}
