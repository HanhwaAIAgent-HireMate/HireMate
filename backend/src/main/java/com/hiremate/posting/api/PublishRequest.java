package com.hiremate.posting.api;

import jakarta.validation.constraints.NotNull;
import java.time.Instant;

/** 접수 기간. 채용 페이지의 접수 기간이자 자동 마감 기준이다. */
public record PublishRequest(@NotNull Instant openAt, @NotNull Instant closeAt) {
}
