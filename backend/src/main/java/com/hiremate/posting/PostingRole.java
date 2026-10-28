package com.hiremate.posting;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/** 하나의 공고에서 안내하는 직무별 모집 내용. 채용과 전형은 공고 단위로 공통 운영한다. */
public record PostingRole(@NotBlank @Size(max = 100) String name, @NotNull @Size(max = 50) String career,
        @NotNull @Size(max = 10) List<@NotNull @Size(max = 300) String> duties,
        @NotNull @Size(max = 10) List<@NotNull @Size(max = 300) String> qualifications,
        @NotNull @Size(max = 10) List<@NotNull @Size(max = 300) String> preferred) {
}
