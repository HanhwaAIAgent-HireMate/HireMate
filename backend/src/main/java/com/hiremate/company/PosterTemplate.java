package com.hiremate.company;

import com.hiremate.global.JsonText;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/** 기본 레이아웃과 회사 배색으로 저장한 이름 있는 기업 전용 템플릿. */
public record PosterTemplate(UUID id, String name, String template, String mood, String color, int decoration,
        @Schema(nullable = true) String canvasJson) {

    public static String sourceId(String canvasJson) {
        try {
            JsonNode data = JsonText.read(canvasJson, JsonNode.class);
            String id = data == null ? "" : data.path("source").path("id").asString("");
            return id.matches("(canva|templated|generated|orshot):[A-Za-z0-9_-]{1,90}") ? id : "";
        } catch (RuntimeException exception) {
            return "";
        }
    }
}
