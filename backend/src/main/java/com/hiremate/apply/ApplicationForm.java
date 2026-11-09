package com.hiremate.apply;

/**
 * 공통 지원서 (기획 v7 §7). 파일이 없으면 null이다.
 */
public record ApplicationForm(String name, String email, String phone, String certificates, boolean consentPrivacy,
        boolean consentAi, Upload resume, Upload coverLetter, Upload portfolio, Upload photo) {

    public record Upload(String fileName, byte[] content) {
    }
}
