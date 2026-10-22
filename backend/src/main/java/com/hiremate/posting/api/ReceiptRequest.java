package com.hiremate.posting.api;

import com.hiremate.posting.ReceiptTemplate;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 접수 확인 메일 수정. 길이는 job_postings 테이블과 같다. */
public record ReceiptRequest(@NotBlank @Size(max = 200) String subject, @NotBlank @Size(max = 5000) String body) {

    public ReceiptTemplate toTemplate() {
        return new ReceiptTemplate(subject.strip(), body.strip());
    }
}
