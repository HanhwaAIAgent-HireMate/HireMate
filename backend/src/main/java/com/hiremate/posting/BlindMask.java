package com.hiremate.posting;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * 블라인드 채용에서 지원 서류의 학교 이름과 학점 숫자를 가린다. 지원서를 받을 때 추출한 본문에 쓰고, 원본 PDF는 바꾸지 않는다.
 * 학교 이름 모양(한빛대학교, 한빛고등학교, Hanbit University), 전국 대학 · 전문대학 이름과 줄임말(school-names.txt),
 * 학과 · 졸업 같은 말 앞의 "○○대"를 찾는다. 연대, 고대, 홍대, 교대처럼 다른 뜻으로 많이 쓰는 줄임말은 문맥이 있을 때만 가린다.
 */
public final class BlindMask {

    /** 가린 자리에 넣는 말. 학교 수준(대학, 고등학교)도 드러나지 않게 하나로 쓴다. */
    public static final String MASK = "○○학교";

    /**
     * 줄임말 뒤에 올 수 있는 말. 서울대입구역의 "서울대"처럼 다른 낱말의 일부는 가리지 않는다.
     * "로"는 넣지 않는다. 주소의 강남대로를 강남대로 보지 않기 위해서다.
     */
    private static final String AFTER = "(?=$|[^가-힣]|에서|에|의|를|을|는|은|이|가|와|과|으로|도|만|생|출신|졸업|재학|휴학"
            + "|학부|학과|대학원|동문)";

    /** 목록 이름에서 만들 수 없는 줄임말. */
    private static final List<String> EXTRA = List.of("카이스트", "포스텍", "유니스트", "지스트", "디지스트", "코리아텍", "외대",
            "시립대", "항공대", "한국공대", "방송대", "방통대", "한예종");

    /** 이름 끝을 줄여 쓰는 말. 이화여자대학교는 이화여대, 서울교육대학교는 서울교대로 쓴다. */
    private static final Map<String, String> SHORT = Map.of("여자", "여", "교육", "교", "외국어", "외", "공과", "공",
            "과학기술", "과기");

    private static final Pattern SCHOOL = Pattern.compile(String.join("|",
            // 학교 이름 모양. 한빛대학교, 한빛과학기술원, 한빛고등학교, 육군사관학교
            "[가-힣]{2,}(?:대학교|대학원|대학|과학기술원|학교)",
            // 목록의 학교 이름과 줄임말. 서울대, 이화여대, 서울교대
            dictionary(),
            // 고등학교 줄임말. 한빛과학고, 한빛외고, 한빛여고
            "[가-힣]+(?:과학고|외국어고|외고|국제고|예술고|여고)" + AFTER,
            // 학과, 졸업 같은 말 앞의 대학 줄임말. 한빛대 컴퓨터공학과, 한빛대 졸업
            "[가-힣]{1,5}대(?=\\s*(?:[가-힣]{0,10}(?:학과|학부|전공|대학원)|졸업|재학|휴학|출신|동아리|캡스톤|학생회|교내|동문))",
            // 영어 학교 이름. Hanbit University, University of Hanbit, Hanbit High School, KAIST
            "(?:[A-Z][A-Za-z.&'-]*\\s+){1,5}"
                    + "(?:University|College|High School|Institute of (?:Science and )?Technology)\\b",
            "\\bUniversity of(?:\\s+[A-Z][A-Za-z.&'-]*){1,4}",
            "\\b(?:KAIST|POSTECH|UNIST|DGIST|GIST|SNU)\\b"));

    /** 학점 숫자. "학점 4.1/4.5", "GPA: 3.9"처럼 이름 뒤의 숫자와, 이름 없이 쓴 "4.1/4.5" 같은 만점 표기를 찾는다. */
    private static final Pattern GRADE = Pattern.compile(
            "(학점|평점|GPA)(\\s*[:：]?\\s*)\\d(?:\\.\\d{1,2})?(?:\\s*/\\s*\\d(?:\\.\\d{1,2})?)?"
                    + "|(?<![\\d.])\\d\\.\\d{1,2}\\s*/\\s*4\\.[035]\\d?(?![\\d.])");

    /** 가린 학점 자리에 넣는 말. */
    private static final String GRADE_MASK = "○○";

    /** 본문을 문장으로 나누는 자리. PDF 글은 줄바꿈이 많아 줄도 문장 끝으로 본다. */
    private static final Pattern SENTENCE = Pattern.compile("\\R|(?<=[.!?])\\s+");

    /** 문장 앞의 글머리 기호. 가린 학교 이름의 "○"는 지우지 않는다. */
    private static final Pattern BULLET = Pattern.compile("^[-–—•·*▪●◦]+\\s*");

    /**
     * 학교를 다녔다는 문맥. "○○학교 행정실 근무"처럼 학교에서 일한 경력은 출신 학교가 아니라 세지 않는다.
     * "○○학교 출신 동료"처럼 다른 사람의 출신 학교도 지원자 본인 이야기가 아니라 세지 않는다.
     * "수강 신청 시스템"은 학교에서 일한 경력에 자주 나오는 업무 이름이라 수강으로 세지 않는다.
     */
    private static final Pattern ATTENDED = Pattern.compile(
            "졸업|재학|휴학|입학|편입|수료|학과|학부|전공|다니|다녔|공부|수강(?!\\s*신청)|캡스톤|동아리|학생회|동문|학번|학년"
                    + "|출신(?!\\s*(?:동료|친구|선배|후배|동기|팀원|직원|개발자|학생|분들?|사람|멘토|교수|선생))"
                    + "|(?i:\\b(?:graduat\\w*|studied|studying|major\\w*|attended|alumn\\w*|enrolled)\\b)");

    /** 가린 지원자 이름 · 이메일 · 전화번호 자리에 넣는 말. */
    public static final String APPLICANT_MASK = "○○○";

    private static final Pattern EMAIL_ADDRESS = Pattern.compile("[\\w.+-]+@[\\w-]+(?:\\.[\\w-]+)+");

    private static final Pattern PHONE_NUMBER = Pattern.compile("(?<!\\d)0\\d{1,2}[-. ]?\\d{3,4}[-. ]?\\d{4}(?!\\d)");

    /** 성을 뺀 이름 뒤에 올 수 있는 말. "다온커머스"처럼 이름으로 시작하는 다른 낱말은 가리지 않는다. */
    private static final String NAME_AFTER = "(?=$|[^가-힣]|이|가|은|는|을|를|의|에게|님|와|과|도|로|으로|입니다|이에요|예요)";

    /** 저장할 때 가린 학점 자리. "학점 ○○"처럼 학점이라는 말 뒤에 남는다. */
    private static final Pattern MASKED_GRADE = Pattern.compile("(?:학점|평점|GPA)\\s*[:：]?\\s*" + GRADE_MASK);

    private BlindMask() {
    }

    /**
     * 저장할 때 가린 정보 가운데 원본 PDF에는 그대로 있는 것 ("출신 학교", "학점"). 블라인드 채용에서 HR이 원본을 열기 전에
     * 알린다. 이름은 이력서에 쓰는 게 자연스러워 알리지 않는다.
     */
    public static List<String> hiddenOnOriginal(String savedText) {
        List<String> kinds = new ArrayList<>();
        if (savedText.contains(MASK)) {
            kinds.add("출신 학교");
        }
        if (MASKED_GRADE.matcher(savedText).find()) {
            kinds.add("학점");
        }
        return kinds;
    }

    /**
     * 지원서에 적은 이름(성을 뺀 이름과 영문 이름의 낱말 포함), 이메일, 전화번호를 가린 본문. 블라인드 채용에서 마지막 전형
     * 결과를 확정하기 전까지 HR · 면접관 · AI에 서류 본문을 줄 때 쓴다. 저장한 본문은 바꾸지 않는다.
     */
    public static String maskApplicant(String text, String name) {
        String masked = EMAIL_ADDRESS.matcher(text).replaceAll(APPLICANT_MASK);
        masked = PHONE_NUMBER.matcher(masked).replaceAll(APPLICANT_MASK);
        String trimmed = name == null ? "" : name.strip();
        if (trimmed.isEmpty()) {
            return masked;
        }
        List<String> patterns = new ArrayList<>();
        patterns.add(Pattern.quote(trimmed));
        if (trimmed.matches("[가-힣]{3,4}")) {
            patterns.add("(?<![가-힣])" + Pattern.quote(trimmed.substring(1)) + NAME_AFTER);
        }
        for (String word : trimmed.split("\\s+")) {
            if (word.matches("[A-Za-z]{2,}")) {
                patterns.add("(?i)\\b" + Pattern.quote(word) + "\\b");
            }
        }
        for (String pattern : patterns) {
            masked = Pattern.compile(pattern).matcher(masked).replaceAll(APPLICANT_MASK);
        }
        return masked;
    }

    /** 본문에서 찾은 학교 이름. 같은 이름은 한 번만, 나온 순서대로 돌려준다. 블라인드 채용 지원자에게 제출 전에 알린다. */
    public static List<String> schoolNames(String text) {
        return SCHOOL.matcher(text).results().map(match -> match.group().strip()).distinct().toList();
    }

    /**
     * 가린 본문에서 학교를 다닌 문맥으로 "○○학교"가 나오는 문장. 블라인드 채용인데 출신 학교를 쓴 서류를 HR에게 알린다.
     * 학교 이름은 가린 채로 보여 주므로 HR은 어느 학교인지 모른 채 판단한다.
     */
    public static List<String> attendedSentences(String masked) {
        return SENTENCE.splitAsStream(masked)
                .map(sentence -> BULLET.matcher(sentence.strip()).replaceFirst(""))
                .filter(sentence -> sentence.contains(MASK) && ATTENDED.matcher(sentence).find())
                .distinct()
                .toList();
    }

    /** 학교 이름을 MASK로, 학점 숫자를 GRADE_MASK로 바꾼 본문. 가릴 것이 없으면 그대로 돌려준다. */
    public static String mask(String text) {
        String masked = SCHOOL.matcher(text).replaceAll(MASK);
        return GRADE.matcher(masked).replaceAll(match -> match.group(1) == null ? GRADE_MASK
                : match.group(1) + (match.group(2).isEmpty() ? " " : match.group(2)) + GRADE_MASK);
    }

    /** 목록의 이름과 줄임말. 같은 자리에서 긴 이름을 먼저 본다 (한국외대를 외대보다 먼저). */
    private static String dictionary() {
        Set<String> names = new LinkedHashSet<>();
        Set<String> abbreviations = new LinkedHashSet<>(EXTRA);
        for (String name : listed()) {
            names.add(name);
            String stem = name.replaceFirst("(?:대학교|대학)$", "");
            if (stem.equals(name) || stem.contains(" ")) {
                continue;
            }
            String base = stem.replaceFirst("^국립", "");
            abbreviations.add(base + "대");
            SHORT.forEach((full, shortened) -> {
                if (base.endsWith(full)) {
                    abbreviations.add(base.substring(0, base.length() - full.length()) + shortened + "대");
                }
            });
        }
        abbreviations.removeIf(abbreviation -> abbreviation.length() < 3 && !EXTRA.contains(abbreviation));
        return "(?:" + quoted(names) + ")|(?:" + quoted(abbreviations) + ")" + AFTER;
    }

    private static String quoted(Set<String> words) {
        return words.stream()
                .sorted(Comparator.comparingInt(String::length).reversed())
                .map(Pattern::quote)
                .collect(Collectors.joining("|"));
    }

    private static List<String> listed() {
        try (InputStream in = BlindMask.class.getResourceAsStream("/school-names.txt")) {
            if (in == null) {
                throw new IllegalStateException("school-names.txt is missing.");
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).lines()
                    .map(String::strip)
                    .filter(line -> !line.isEmpty() && !line.startsWith("#"))
                    .toList();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
