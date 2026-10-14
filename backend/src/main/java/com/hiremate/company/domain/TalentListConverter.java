package com.hiremate.company.domain;

import com.hiremate.company.Talent;
import com.hiremate.global.JsonText;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.util.ArrayList;
import java.util.List;
import tools.jackson.core.type.TypeReference;

@Converter
class TalentListConverter implements AttributeConverter<List<Talent>, String> {

    @Override
    public String convertToDatabaseColumn(List<Talent> talents) {
        return JsonText.write(talents == null ? List.of() : talents);
    }

    @Override
    public List<Talent> convertToEntityAttribute(String json) {
        List<Talent> talents = JsonText.read(json, new TypeReference<List<Talent>>() { });
        return talents == null ? new ArrayList<>() : new ArrayList<>(talents);
    }
}
