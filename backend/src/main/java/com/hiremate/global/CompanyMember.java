package com.hiremate.global;

import java.util.UUID;

/** 같은 기업의 계정 하나. 업무 모듈이 면접관 지정 · 이름 표시에 쓴다. */
public record CompanyMember(UUID memberId, String name, String email, boolean hr) {
}
