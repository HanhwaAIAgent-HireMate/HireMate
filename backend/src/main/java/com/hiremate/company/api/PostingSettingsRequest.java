package com.hiremate.company.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public record PostingSettingsRequest(
        @NotNull @Size(max = 1000) String writingStyle,
        @NotNull @Size(max = 10) List<@NotBlank @Size(max = 200) String> requiredNotices) {
}
