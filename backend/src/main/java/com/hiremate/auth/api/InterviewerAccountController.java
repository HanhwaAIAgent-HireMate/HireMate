package com.hiremate.auth.api;

import com.hiremate.auth.application.InterviewerAccountService;
import com.hiremate.auth.domain.Member;
import com.hiremate.global.AuthenticatedMember;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 기업 설정의 면접관 계정. HR만 쓴다(`/api/companies/**`는 HR 역할에만 열려 있다). */
@RestController
@RequestMapping("/api/companies/me/interviewers")
public class InterviewerAccountController {

    private final InterviewerAccountService accounts;

    public InterviewerAccountController(InterviewerAccountService accounts) {
        this.accounts = accounts;
    }

    @GetMapping
    public List<InterviewerAccount> interviewers(AuthenticatedMember member) {
        return accounts.interviewers(member.companyId()).stream().map(InterviewerAccount::from).toList();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public InterviewerAccount create(AuthenticatedMember member, @Valid @RequestBody CreateRequest request) {
        return InterviewerAccount.from(accounts.create(member.companyId(), request.name(), request.email(),
                request.password()));
    }

    public record InterviewerAccount(UUID memberId, String name, String email, Instant createdAt) {

        static InterviewerAccount from(Member member) {
            return new InterviewerAccount(member.getId(), member.getName(), member.getEmail(), member.getCreatedAt());
        }
    }

    public record CreateRequest(@NotBlank @Size(max = 100) String name,
            @NotBlank @Email @Size(max = 254) String email,
            @NotBlank @Size(min = 12, max = 128) String password) {
    }
}
