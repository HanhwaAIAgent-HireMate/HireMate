package com.hiremate.posting;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * HR이 직접 고치거나 AI 수정 요청으로 고치는 공고 본문. 전형 절차와 필수 제출 서류는 따로 다룬다.
 * headcount부터는 모집 조건이다. 채용 인원은 정하지 않았으면 null이고, 나머지 모집 조건은 비어 있으면 빈 문자열이다.
 * blind는 블라인드 채용이다. 켜면 학력 · 출신 학교를 공고와 AI 판단에 쓰지 않는다. 공고 본문을 받는 모든 Agent가 같이 보도록
 * 본문에 둔다. HR은 공고 저장 요청의 blind로만 바꾸고, 본문을 저장할 때나 수정안을 적용할 때는 바뀌지 않는다.
 */
public record PostingContent(String title, String jobCategory, String employmentType, String career,
        String location, String intro, List<String> duties, List<String> qualifications, List<String> preferred,
        List<String> benefits, @Schema(nullable = true) Integer headcount, String position, String education,
        String workHours, String salary,
        @Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED) List<PostingRole> roles,
        @Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED) boolean blind) {

    /** 모집 조건이 없던 때 저장한 수정안(JSON)도 읽을 수 있게 빈 칸을 빈 문자열로 둔다. */
    public PostingContent {
        position = position == null ? "" : position;
        education = education == null ? "" : education;
        workHours = workHours == null ? "" : workHours;
        salary = salary == null ? "" : salary;
        roles = roles == null ? List.of() : List.copyOf(roles);
    }

    /** 블라인드가 아닌 본문. */
    public PostingContent(String title, String jobCategory, String employmentType, String career,
            String location, String intro, List<String> duties, List<String> qualifications, List<String> preferred,
            List<String> benefits, Integer headcount, String position, String education,
            String workHours, String salary, List<PostingRole> roles) {
        this(title, jobCategory, employmentType, career, location, intro, duties, qualifications, preferred,
                benefits, headcount, position, education, workHours, salary, roles, false);
    }

    public PostingContent(String title, String jobCategory, String employmentType, String career,
            String location, String intro, List<String> duties, List<String> qualifications, List<String> preferred,
            List<String> benefits, Integer headcount, String position, String education,
            String workHours, String salary) {
        this(title, jobCategory, employmentType, career, location, intro, duties, qualifications, preferred,
                benefits, headcount, position, education, workHours, salary, List.of());
    }

    /** 모집 조건 없이 만든다. 모집 조건은 비워 둔다. */
    public PostingContent(String title, String jobCategory, String employmentType, String career, String location,
            String intro, List<String> duties, List<String> qualifications, List<String> preferred,
            List<String> benefits) {
        this(title, jobCategory, employmentType, career, location, intro, duties, qualifications, preferred, benefits,
                null, "", "", "", "");
    }
}
