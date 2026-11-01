package com.hiremate.auth.application;

import com.hiremate.auth.MemberRole;
import com.hiremate.auth.domain.MemberRepository;
import com.hiremate.global.ApiException;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 배정 가능한 기존 계정만 조회한다. 면접 역할 배정이 계정의 HR 권한을 바꾸지는 않는다. */
@Service
public class InterviewMemberDirectory {

    private final MemberRepository members;

    public InterviewMemberDirectory(MemberRepository members) {
        this.members = members;
    }

    @Transactional(readOnly = true)
    public List<InterviewMemberChoice> list(UUID companyId) {
        return members.findByCompanyIdOrderByName(companyId).stream()
                .map(member -> new InterviewMemberChoice(member.getId(), member.getName(), member.getEmail(),
                        member.getRole())).toList();
    }

    @Transactional(readOnly = true)
    public void requireMember(UUID companyId, UUID memberId) {
        members.findByIdAndCompanyId(memberId, companyId).orElseThrow(
                () -> new ApiException(HttpStatus.BAD_REQUEST, "INVALID_INTERVIEWER",
                        "Assign an existing member of this company."));
    }

    public record InterviewMemberChoice(UUID memberId, String name, String email, MemberRole accountRole) {
    }
}
