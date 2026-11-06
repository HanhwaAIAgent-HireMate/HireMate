package com.hiremate.apply;

import java.util.UUID;

/**
 * 지원자의 실제 이름과 이메일. 블라인드 채용에서도 가리지 않는다. 지원자에게 메일을 보내거나 외부 평가 결과를 이메일로 맞출 때만
 * 쓰고, HR · 면접관 화면이나 AI로 넘기지 않는다. 화면과 AI에는 {@link ApplicantInfo}를 쓴다.
 */
public record ApplicantContact(UUID applicationId, int applicationNo, String name, String email) {
}
