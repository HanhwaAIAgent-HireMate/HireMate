package com.hiremate.posting;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class SchoolNamesTests {

    @Test
    @DisplayName("학교 이름, 약칭, 학과 앞의 대학 약칭을 가린다")
    void masksSchoolNames() {
        assertThat(SchoolNames.mask("한빛대학교 캡스톤 프로젝트에서 결제 앱을 만들었습니다."))
                .isEqualTo("○○학교 캡스톤 프로젝트에서 결제 앱을 만들었습니다.");
        assertThat(SchoolNames.mask("한빛과학고를 거쳐 서울대에서 컴퓨터공학을 공부했습니다."))
                .isEqualTo("○○학교를 거쳐 ○○학교에서 컴퓨터공학을 공부했습니다.");
        assertThat(SchoolNames.mask("카이스트 전산학부 졸업")).isEqualTo("○○학교 전산학부 졸업");
        assertThat(SchoolNames.mask("한빛대 컴퓨터공학과 졸업, 연대 경영학과 복수전공"))
                .isEqualTo("○○학교 컴퓨터공학과 졸업, ○○학교 경영학과 복수전공");
        assertThat(SchoolNames.mask("Graduated from Hanbit University and KAIST."))
                .isEqualTo("Graduated from ○○학교 and ○○학교.");
    }

    @Test
    @DisplayName("전국 대학 목록의 줄임말은 학과 같은 말이 없어도 가린다")
    void masksListedAbbreviations() {
        assertThat(SchoolNames.mask("대구대에서 공부했고 이화여대, 서울교대, 한국외대 학생들과 협업했습니다."))
                .isEqualTo("○○학교에서 공부했고 ○○학교, ○○학교, ○○학교 학생들과 협업했습니다.");
        assertThat(SchoolNames.mask("국립부경대학교와 명지전문대를 거쳤습니다.")).isEqualTo("○○학교와 ○○학교를 거쳤습니다.");
    }

    @Test
    @DisplayName("학교가 아닌 말과 다른 뜻의 약칭은 그대로 둔다")
    void keepsOtherWords() {
        String text = "서울대입구역 근처 카페를 운영했고, 학교 폭력 예방 캠페인과 시민 연대 활동, 고대 문명 동아리를 했습니다. "
                + "교대 근무로 MIT License 프로젝트를 관리했습니다. 주소는 서울 강남구 강남대로 123입니다.";
        assertThat(SchoolNames.mask(text)).isEqualTo(text);
    }
}
