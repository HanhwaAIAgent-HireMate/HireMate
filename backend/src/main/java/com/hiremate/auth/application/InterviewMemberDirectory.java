package com.hiremate.auth.application;

import com.hiremate.auth.MemberRole;
import com.hiremate.auth.domain.MemberRepository;
import com.hiremate.global.ApiException;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 면접관으로 배정할 수 있는 계정: 같은 기업의 면접관 계정만. HR 계정은 면접관으로 배정하지 않는다
 * (채용 담당자가 직접 면접을 보려면 설정 › 면접관에서 면접관 계정을 만든다).
 */
@Service
public class InterviewMemberDirectory {

    private final MemberRepository members;

    public InterviewMemberDirectory(MemberRepository members) {
        this.members = members;
    }

    @Transactional(readOnly = true)
    public List<InterviewMemberChoice> list(UUID companyId) {
        return members.findByCompanyIdOrderByName(companyId).stream()
                .filter(member -> member.getRole() == MemberRole.INTERVIEWER)
                .map(member -> new InterviewMemberChoice(member.getId(), member.getName(), member.getEmail(),
                        member.getRole())).toList();
    }

    @Transactional(readOnly = true)
    public void requireMember(UUID companyId, UUID memberId) {
        members.findByIdAndCompanyId(memberId, companyId)
                .filter(member -> member.getRole() == MemberRole.INTERVIEWER)
                .orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST, "INVALID_INTERVIEWER",
                        "Assign an interviewer account of this company."));
    }

    public record InterviewMemberChoice(UUID memberId, String name, String email, MemberRole accountRole) {
    }
}
