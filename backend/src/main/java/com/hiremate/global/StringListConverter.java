package com.hiremate.global;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.util.ArrayList;
import java.util.List;
import tools.jackson.core.type.TypeReference;

/** 문자열 목록을 TEXT 컬럼에 JSON 배열로 저장한다. {@code @Convert(converter = StringListConverter.class)}로 쓴다. */
@Converter
public class StringListConverter implements AttributeConverter<List<String>, String> {

    @Override
    public String convertToDatabaseColumn(List<String> values) {
        return JsonText.write(values == null ? List.of() : values);
    }

    @Override
    public List<String> convertToEntityAttribute(String json) {
        List<String> values = JsonText.read(json, new TypeReference<List<String>>() { });
        return values == null ? new ArrayList<>() : new ArrayList<>(values);
    }
}
