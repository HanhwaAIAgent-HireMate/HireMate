package com.hiremate.posting;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * 한글 이름의 흔한 영문 표기. 지원서 이름 칸은 한글인데 이력서를 영문으로 쓴 지원자(노유나 → Yuna Noh)의 이름을 블라인드
 * 채용에서 가릴 때 쓴다. 영문 표기는 사람마다 달라 흔한 모양만 찾는다.
 */
final class RomanizedName {

    /** 초성. 이름에 흔한 두 가지 표기를 함께 둔다 (ㄱ: g · k). */
    private static final String[][] INITIALS = {{"g", "k"}, {"kk"}, {"n"}, {"d", "t"}, {"tt"}, {"r", "l"}, {"m"},
        {"b", "p"}, {"pp"}, {"s"}, {"ss"}, {""}, {"j"}, {"jj"}, {"ch"}, {"k"}, {"t"}, {"p"}, {"h"}};

    /** 중성. ㅓ는 eo · u, ㅜ는 u · oo처럼 이름에 흔한 표기를 함께 둔다. */
    private static final String[][] MEDIALS = {{"a"}, {"ae"}, {"ya"}, {"yae"}, {"eo", "u"}, {"e"}, {"yeo", "yu"},
        {"ye"}, {"o"}, {"wa"}, {"wae"}, {"oe"}, {"yo"}, {"u", "oo"}, {"wo"}, {"we"}, {"wi"}, {"yu"}, {"eu", "u"},
        {"ui"}, {"i"}};

    /** 종성. 이름에 흔한 받침만 두 가지 표기를 함께 둔다. */
    private static final String[][] FINALS = {{""}, {"k", "g"}, {"k"}, {"k"}, {"n"}, {"n"}, {"n"}, {"t"}, {"l"},
        {"k"}, {"m"}, {"p"}, {"l"}, {"l"}, {"p"}, {"l"}, {"m"}, {"p", "b"}, {"p"}, {"t"}, {"t"}, {"ng"}, {"t"},
        {"t"}, {"k"}, {"t"}, {"p"}, {"t"}};

    /** 흔한 성의 영문 표기. 목록에 없는 성은 위 표로 바꾼다. */
    private static final Map<Character, List<String>> SURNAMES = Map.ofEntries(
            Map.entry('김', List.of("kim", "gim")), Map.entry('이', List.of("lee", "yi", "rhee", "ree", "i")),
            Map.entry('박', List.of("park", "pak", "bak")), Map.entry('최', List.of("choi", "choe")),
            Map.entry('정', List.of("jung", "jeong", "chung")), Map.entry('강', List.of("kang", "gang")),
            Map.entry('조', List.of("cho", "jo")), Map.entry('윤', List.of("yoon", "yun")),
            Map.entry('장', List.of("jang", "chang")), Map.entry('임', List.of("lim", "im", "yim")),
            Map.entry('오', List.of("oh", "o")), Map.entry('서', List.of("seo", "suh")),
            Map.entry('신', List.of("shin", "sin")), Map.entry('권', List.of("kwon", "gwon")),
            Map.entry('안', List.of("ahn", "an")), Map.entry('류', List.of("ryu", "yoo", "yu")),
            Map.entry('유', List.of("yoo", "yu")), Map.entry('전', List.of("jeon", "jun", "chun")),
            Map.entry('고', List.of("ko", "go")), Map.entry('문', List.of("moon", "mun")),
            Map.entry('손', List.of("son", "sohn")), Map.entry('백', List.of("baek", "paik", "back")),
            Map.entry('허', List.of("heo", "huh")), Map.entry('심', List.of("sim", "shim")),
            Map.entry('노', List.of("noh", "roh", "no")), Map.entry('성', List.of("sung", "seong")),
            Map.entry('주', List.of("joo", "ju")), Map.entry('우', List.of("woo", "u")),
            Map.entry('구', List.of("koo", "gu")), Map.entry('나', List.of("na", "ra")),
            Map.entry('엄', List.of("eom", "um")), Map.entry('천', List.of("cheon", "chun")),
            Map.entry('공', List.of("kong", "gong")), Map.entry('현', List.of("hyun", "hyeon")),
            Map.entry('변', List.of("byun", "byeon")), Map.entry('추', List.of("choo", "chu")),
            Map.entry('석', List.of("seok", "suk")), Map.entry('선', List.of("sun", "seon")),
            Map.entry('길', List.of("gil", "kil")), Map.entry('연', List.of("yeon", "youn")),
            Map.entry('명', List.of("myung", "myeong")), Map.entry('기', List.of("ki", "gi")),
            Map.entry('금', List.of("keum", "geum")), Map.entry('육', List.of("yook", "yuk")),
            Map.entry('국', List.of("kook", "guk")), Map.entry('경', List.of("kyung", "gyeong")),
            Map.entry('부', List.of("boo", "bu")), Map.entry('범', List.of("bum", "beom")));

    private RomanizedName() {
    }

    /**
     * 영문으로 쓴 이름을 찾는 패턴. 이름(성 제외)이 네 글자 이상이면 혼자 나와도 찾고, 짧으면 성과 붙어 나올 때만 찾는다
     * ("In"처럼 짧은 이름은 영어 낱말과 겹친다). 성은 이름 앞뒤에 붙어 있을 때 함께 가린다.
     */
    static List<Pattern> patterns(String name) {
        if (!name.matches("[가-힣]{2,4}")) {
            return List.of();
        }
        String surnames = alternation(surname(name.charAt(0)));
        String givens = alternation(given(name.substring(1)));
        String separator = "[\\s,.-]+";
        // 이메일 주소(kim.gaon@example.com) 안의 글자는 연락에 필요해 가리지 않는다
        String notEmail = "(?![\\w.+-]*@)";
        List<Pattern> patterns = new ArrayList<>();
        patterns.add(Pattern.compile("(?i)\\b(?:" + surnames + ")" + separator + "(?:" + givens + ")\\b" + notEmail));
        patterns.add(Pattern.compile("(?i)\\b(?:" + givens + ")" + separator + "(?:" + surnames + ")\\b" + notEmail));
        Set<String> longGivens = given(name.substring(1)).stream()
                .filter(given -> given.replaceAll("[\\s-]", "").length() >= 4)
                .collect(Collectors.toCollection(LinkedHashSet::new));
        if (!longGivens.isEmpty()) {
            patterns.add(Pattern.compile("(?i)\\b(?:" + alternation(longGivens) + ")\\b" + notEmail));
        }
        return patterns;
    }

    /** 성의 영문 표기. */
    static Set<String> surname(char surname) {
        List<String> listed = SURNAMES.get(surname);
        return listed != null ? new LinkedHashSet<>(listed) : syllable(surname);
    }

    /** 이름(성 제외)의 영문 표기. 붙여 쓰기, 하이픈, 띄어쓰기를 모두 둔다 (Yuna, Yu-na, Yu Na). */
    static Set<String> given(String given) {
        List<Set<String>> syllables = given.chars().mapToObj(c -> syllable((char) c)).toList();
        Set<String> joined = new LinkedHashSet<>(List.of(""));
        Set<String> hyphen = new LinkedHashSet<>(List.of(""));
        for (int i = 0; i < syllables.size(); i++) {
            boolean first = i == 0;
            joined = combine(joined, syllables.get(i), "");
            hyphen = combine(hyphen, syllables.get(i), first ? "" : "-");
        }
        Set<String> all = new LinkedHashSet<>(joined);
        all.addAll(hyphen);
        hyphen.forEach(name -> all.add(name.replace("-", " ")));
        return all;
    }

    private static Set<String> combine(Set<String> heads, Set<String> tails, String separator) {
        Set<String> combined = new LinkedHashSet<>();
        for (String head : heads) {
            for (String tail : tails) {
                combined.add(head + (head.isEmpty() ? "" : separator) + tail);
            }
        }
        return combined;
    }

    /** 한 글자의 영문 표기들. */
    private static Set<String> syllable(char syllable) {
        int code = syllable - 0xAC00;
        if (code < 0 || code > 11171) {
            return Set.of();
        }
        Set<String> spelled = new LinkedHashSet<>();
        for (String initial : INITIALS[code / 588]) {
            for (String medial : MEDIALS[code % 588 / 28]) {
                for (String last : FINALS[code % 28]) {
                    spelled.add(initial + medial + last);
                }
            }
        }
        return spelled;
    }

    private static String alternation(Set<String> words) {
        return words.stream()
                .sorted((left, right) -> right.length() - left.length())
                .map(word -> Pattern.quote(word).replace(" ", "\\E\\s+\\Q").replace("-", "\\E[\\s-]?\\Q"))
                .collect(Collectors.joining("|"));
    }
}
