package com.hiremate.apply;

/** 접수 완료 화면에 보여 줄 내용. */
public record SubmittedApplication(int applicationNo, String name, String companyName, String postingTitle) {
}
