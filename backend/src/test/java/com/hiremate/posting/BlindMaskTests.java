package com.hiremate.posting;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class BlindMaskTests {

    @Test
    @DisplayName("학교 이름, 약칭, 학과 앞의 대학 약칭을 가린다")
    void masksSchoolNames() {
        assertThat(BlindMask.mask("한빛대학교 캡스톤 프로젝트에서 결제 앱을 만들었습니다."))
                .isEqualTo("○○학교 캡스톤 프로젝트에서 결제 앱을 만들었습니다.");
        assertThat(BlindMask.mask("한빛과학고를 거쳐 서울대에서 컴퓨터공학을 공부했습니다."))
                .isEqualTo("○○학교를 거쳐 ○○학교에서 컴퓨터공학을 공부했습니다.");
        assertThat(BlindMask.mask("카이스트 전산학부 졸업")).isEqualTo("○○학교 전산학부 졸업");
        assertThat(BlindMask.mask("한빛대 컴퓨터공학과 졸업, 연대 경영학과 복수전공"))
                .isEqualTo("○○학교 컴퓨터공학과 졸업, ○○학교 경영학과 복수전공");
        assertThat(BlindMask.mask("Graduated from Hanbit University and KAIST."))
                .isEqualTo("Graduated from ○○학교 and ○○학교.");
    }

    @Test
    @DisplayName("전국 대학 목록의 줄임말은 학과 같은 말이 없어도 가린다")
    void masksListedAbbreviations() {
        assertThat(BlindMask.mask("대구대에서 공부했고 이화여대, 서울교대, 한국외대 학생들과 협업했습니다."))
                .isEqualTo("○○학교에서 공부했고 ○○학교, ○○학교, ○○학교 학생들과 협업했습니다.");
        assertThat(BlindMask.mask("국립부경대학교와 명지전문대를 거쳤습니다.")).isEqualTo("○○학교와 ○○학교를 거쳤습니다.");
        assertThat(BlindMask.mask("강릉원주대에서 공부하고 경희사이버대를 다녔습니다."))
                .isEqualTo("○○학교에서 공부하고 ○○학교를 다녔습니다.");
        assertThat(BlindMask.mask("Studied at Gwangju Institute of Science and Technology."))
                .isEqualTo("Studied at ○○학교.");
    }

    @Test
    @DisplayName("학점 숫자를 가리고 학점이라는 말은 남긴다")
    void masksGrades() {
        assertThat(BlindMask.mask("한빛대학교 컴퓨터공학과 2018.03 ~ 2022.02 졸업, 학점 4.1/4.5"))
                .isEqualTo("○○학교 컴퓨터공학과 2018.03 ~ 2022.02 졸업, 학점 ○○");
        assertThat(BlindMask.mask("학점 4.1로 졸업했고 GPA: 3.9 / 4.3, 평점3.5였습니다. 전공 성적 3.8/4.5"))
                .isEqualTo("학점 ○○로 졸업했고 GPA: ○○, 평점 ○○였습니다. 전공 성적 ○○");
    }

    @Test
    @DisplayName("서류에서 찾은 학교 이름을 한 번씩 나온 순서대로 알려 준다")
    void findsSchoolNames() {
        assertThat(BlindMask.schoolNames("한빛대학교 컴퓨터공학과 졸업\n서울대와 협업했고 한빛대학교 동아리 회장을 했습니다."))
                .containsExactly("한빛대학교", "서울대");
        assertThat(BlindMask.schoolNames("Java와 Spring Boot로 정산 API를 개발했습니다.")).isEmpty();
    }

    @Test
    @DisplayName("가린 본문에서 학교를 다닌 문맥의 문장만 찾고, 학교에서 일한 경력은 세지 않는다")
    void findsAttendedSentences() {
        String masked = "○○학교 컴퓨터공학과 2018.03 ~ 2022.02 졸업\n"
                + "○○학교 행정실에서 2년 근무했습니다. ○○학교에서 데이터베이스를 공부했습니다.\n"
                + "- ○○학교 캡스톤 프로젝트에서 예약 서비스를 만들었습니다.\n"
                + "Java로 정산 API를 개발했습니다.";
        // 글머리 기호는 떼고, 가린 학교 이름의 ○는 남긴다
        assertThat(BlindMask.attendedSentences(masked)).containsExactly("○○학교 컴퓨터공학과 2018.03 ~ 2022.02 졸업",
                "○○학교에서 데이터베이스를 공부했습니다.", "○○학교 캡스톤 프로젝트에서 예약 서비스를 만들었습니다.");
        assertThat(BlindMask.attendedSentences("Graduated from ○○학교 in 2020. Worked with ○○학교 on a payment app."))
                .containsExactly("Graduated from ○○학교 in 2020.");
        // 학교에서 일한 경력의 "수강 신청 시스템"은 세지 않고, 학교에서 수강한 과목은 센다
        assertThat(BlindMask.attendedSentences("○○학교 행정 부서와 수강 신청 시스템의 장애를 줄였습니다. ○○학교에서 네트워크를 수강했습니다."))
                .containsExactly("○○학교에서 네트워크를 수강했습니다.");
        // 다른 사람의 출신 학교는 세지 않고, 본인의 출신 학교는 센다
        assertThat(BlindMask.attendedSentences("○○학교 출신 동료와 코드 리뷰 규칙을 만들었습니다. ○○학교 출신으로 결제 개발을 시작했습니다."))
                .containsExactly("○○학교 출신으로 결제 개발을 시작했습니다.");
    }

    @Test
    @DisplayName("지원자 이름 · 성을 뺀 이름 · 영문 이름을 가리고, 이메일 · 전화번호와 이름으로 시작하는 다른 낱말은 둔다")
    void masksApplicantName() {
        String text = "김가온 | 백엔드 개발자\nkim.gaon@example.com · 010-1234-5678\n"
                + "가온이는 결제 API를 만들었고, 동료들은 가온님이라 불렀습니다. 가온커머스에서 일했습니다.";
        assertThat(BlindMask.maskApplicant(text, "김가온"))
                .isEqualTo("○○○ | 백엔드 개발자\nkim.gaon@example.com · 010-1234-5678\n"
                        + "○○○이는 결제 API를 만들었고, 동료들은 ○○○님이라 불렀습니다. 가온커머스에서 일했습니다.");
        assertThat(BlindMask.maskApplicant("Yuna Noh built the API. noh worked with Yunasoft.", "Yuna Noh"))
                .isEqualTo("○○○ built the API. ○○○ worked with Yunasoft.");
    }

    @Test
    @DisplayName("한글 이름의 흔한 영문 표기도 가리고, 짧은 이름은 성과 붙어 있을 때만 가린다")
    void masksRomanizedName() {
        assertThat(BlindMask.maskApplicant("Yuna Noh | Backend. Noh Yuna, Yu-na Roh and Yunasoft.", "노유나"))
                .isEqualTo("○○○ | Backend. ○○○, ○○○ and Yunasoft.");
        assertThat(BlindMask.maskApplicant("Gaon built it. Kim Ga-on joined Gaonpay.", "김가온"))
                .isEqualTo("○○○ built it. ○○○ joined Gaonpay.");
        // "In"처럼 짧은 이름은 영어 낱말과 겹쳐 성과 붙어 있을 때만 가린다
        assertThat(BlindMask.maskApplicant("Worked in Seoul. Park In led the team.", "박인"))
                .isEqualTo("Worked in Seoul. ○○○ led the team.");
    }

    @Test
    @DisplayName("학교가 아닌 말과 다른 뜻의 약칭, 학점이 아닌 숫자는 그대로 둔다")
    void keepsOtherWords() {
        String text = "서울대입구역 근처 카페를 운영했고, 학교 폭력 예방 캠페인과 시민 연대 활동, 고대 문명 동아리를 했습니다. "
                + "교대 근무로 MIT License 프로젝트를 관리했습니다. 주소는 서울 강남구 강남대로 123입니다. "
                + "학점 관리도 꾸준히 했고, Java 17과 Spring Boot 3.2로 응답 시간을 1.5/2.0초에서 줄였습니다.";
        assertThat(BlindMask.mask(text)).isEqualTo(text);
    }
}
