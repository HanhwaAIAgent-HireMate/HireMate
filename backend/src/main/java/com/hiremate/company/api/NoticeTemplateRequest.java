package com.hiremate.company.api;

import com.hiremate.company.NoticeTemplateInfo;
import com.hiremate.company.NoticeTemplateType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record NoticeTemplateRequest(
        @NotBlank @Size(max = 200) String subject,
        @NotNull @Size(max = 2000) String greeting,
        @NotNull @Size(max = 200) String aiGuide,
        @NotNull @Size(max = 2000) String closing,
        @NotNull @Size(max = 2000) String requiredText) {

    NoticeTemplateInfo toInfo(NoticeTemplateType type) {
        return new NoticeTemplateInfo(type, subject, greeting, aiGuide, closing, requiredText);
    }
}
