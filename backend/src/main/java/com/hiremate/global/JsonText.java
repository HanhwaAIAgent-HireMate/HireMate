package com.hiremate.global;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/** 목록이나 구조를 TEXT 컬럼에 JSON으로 저장할 때 쓴다. Entity의 AttributeConverter에서 호출한다. */
public final class JsonText {

    private static final JsonMapper MAPPER = JsonMapper.builder().build();

    private JsonText() {
    }

    public static String write(Object value) {
        return value == null ? null : MAPPER.writeValueAsString(value);
    }

    public static <T> T read(String json, TypeReference<T> type) {
        return json == null || json.isBlank() ? null : MAPPER.readValue(json, type);
    }

    public static <T> T read(String json, Class<T> type) {
        return json == null || json.isBlank() ? null : MAPPER.readValue(json, type);
    }
}
