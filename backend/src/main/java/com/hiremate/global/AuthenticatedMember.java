package com.hiremate.global;

import java.util.UUID;

/**
 * 요청을 보낸 담당자. 업무 API의 컨트롤러 인자로 받으며, 조회와 변경은 companyId 범위로 제한한다.
 *
 * <p>auth 모듈의 인증 정보가 이 타입을 구현한다. 업무 모듈은 auth 모듈에 의존하지 않고 이 타입만 쓴다.
 */
public interface AuthenticatedMember {

    UUID memberId();

    UUID companyId();

    String name();

    /** HR 담당자인가. 아니면 면접관이다. 업무 모듈은 auth의 역할 대신 이 값으로 권한을 나눈다. */
    boolean hr();
}
