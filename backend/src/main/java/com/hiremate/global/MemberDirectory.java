package com.hiremate.global;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * 같은 기업의 계정 조회. auth 모듈이 구현한다.
 *
 * <p>업무 모듈은 auth 모듈에 의존하지 않고 이 타입만 쓴다 ({@link AuthenticatedMember}와 같은 방식).
 */
public interface MemberDirectory {

    /** 기업의 계정 전체. 만든 순서다. */
    List<CompanyMember> members(UUID companyId);

    Optional<CompanyMember> find(UUID companyId, UUID memberId);
}
