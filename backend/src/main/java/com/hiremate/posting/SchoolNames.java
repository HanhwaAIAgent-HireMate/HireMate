package com.hiremate.posting;

import java.util.regex.Pattern;

/**
 * 블라인드 채용에서 지원 서류의 학교 이름을 가린다. 지원서를 받을 때 추출한 본문에 쓰고, 원본 PDF는 바꾸지 않는다.
 * 학교 이름 모양(한빛대학교, 한빛고등학교, Hanbit University), 자주 쓰는 약칭(서울대, 카이스트),
 * 학과 · 졸업 같은 말 앞의 "○○대"를 찾는다. 연대, 고대, 홍대, 교대처럼 다른 뜻으로 많이 쓰는 약칭은 문맥이 있을 때만 가린다.
 */
public final class SchoolNames {

    /** 가린 자리에 넣는 말. 학교 수준(대학, 고등학교)도 드러나지 않게 하나로 쓴다. */
    public static final String MASK = "○○학교";

    /** 약칭 뒤에 올 수 있는 말. 서울대입구역의 "서울대"처럼 다른 낱말의 일부는 가리지 않는다. */
    private static final String AFTER = "(?=$|[^가-힣]|에서|에|의|를|을|는|은|이|가|와|과|로|으로|도|만|생|출신|졸업|재학|휴학"
            + "|학부|학과|대학원|동문)";

    private static final String ABBREVIATIONS = String.join("|", "서울대", "연세대", "고려대", "카이스트", "포스텍", "포항공대",
            "성균관대", "한양대", "서강대", "중앙대", "경희대", "한국외대", "외대", "서울시립대", "시립대", "이화여대", "건국대", "동국대",
            "홍익대", "숙명여대", "국민대", "숭실대", "세종대", "단국대", "광운대", "명지대", "상명대", "가톨릭대", "서울과기대",
            "항공대", "인하대", "아주대", "한국공대", "코리아텍", "가천대", "경기대", "부산대", "경북대", "전남대", "전북대", "충남대",
            "충북대", "강원대", "제주대", "경상국립대", "부경대", "울산대", "영남대", "계명대", "동아대", "조선대", "한남대", "원광대",
            "순천향대", "한림대", "인제대", "덕성여대", "동덕여대", "서울여대", "성신여대", "한성대", "삼육대", "서경대", "한국교원대",
            "서울교대", "방송대", "방통대", "유니스트", "지스트", "디지스트");

    private static final Pattern SCHOOL = Pattern.compile(String.join("|",
            // 학교 이름 모양. 한빛대학교, 한빛과학기술원, 한빛고등학교, 육군사관학교
            "[가-힣]{2,}(?:대학교|대학원|대학|과학기술원|학교)",
            // 고등학교 약칭. 한빛과학고, 한빛외고, 한빛여고
            "[가-힣]+(?:과학고|외국어고|외고|국제고|예술고|여고)" + AFTER,
            // 자주 쓰는 대학 약칭
            "(?:" + ABBREVIATIONS + ")" + AFTER,
            // 학과, 졸업 같은 말 앞의 대학 약칭. 한빛대 컴퓨터공학과, 한빛대 졸업
            "[가-힣]{1,5}대(?=\\s*(?:[가-힣]{0,10}(?:학과|학부|전공|대학원)|졸업|재학|휴학|출신|동아리|캡스톤|학생회|교내|동문))",
            // 영어 학교 이름. Hanbit University, University of Hanbit, Hanbit High School, KAIST
            "(?:[A-Z][A-Za-z.&'-]*\\s+){1,5}(?:University|College|High School|Institute of Technology)\\b",
            "\\bUniversity of(?:\\s+[A-Z][A-Za-z.&'-]*){1,4}",
            "\\b(?:KAIST|POSTECH|UNIST|DGIST|GIST|SNU)\\b"));

    private SchoolNames() {
    }

    /** 학교 이름을 MASK로 바꾼 본문. 학교 이름이 없으면 그대로 돌려준다. */
    public static String mask(String text) {
        return SCHOOL.matcher(text).replaceAll(MASK);
    }
}
