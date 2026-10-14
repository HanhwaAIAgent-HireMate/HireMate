package com.hiremate.auth.api;

public record CsrfResponse(String token, String headerName, String parameterName) {
}
