package com.hiremate.company.api;

import com.hiremate.company.Talent;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public record ProfileRequest(
        @NotNull @Size(max = 5000) String intro,
        @NotNull @Size(max = 5000) String culture,
        @NotNull @Size(max = 10) List<@Valid TalentItem> talents,
        @NotNull @Size(max = 20) List<@NotBlank @Size(max = 30) String> benefits,
        @Schema(nullable = true, requiredMode = Schema.RequiredMode.NOT_REQUIRED) @Size(max = 200) String address) {

    /** 회사 주소. 빼고 보내면 빈 글로 저장한다. */
    String addressText() {
        return address == null ? "" : address.strip();
    }

    List<Talent> talentList() {
        return talents.stream().map(talent -> new Talent(talent.title().trim(), talent.description().trim())).toList();
    }

    public record TalentItem(@NotBlank @Size(max = 50) String title, @NotNull @Size(max = 200) String description) {
    }
}
