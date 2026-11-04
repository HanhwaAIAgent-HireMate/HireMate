package com.hiremate.apply;

import com.hiremate.posting.DocumentType;
import java.util.List;

/**
 * 원본 PDF를 열면 블라인드로 가린 정보가 보이는 서류.
 *
 * @param kinds 원본에 그대로 있는 출신 학교 · 학점 (예: "출신 학교", "학점"). 지원자가 블라인드 원칙과 달리 적은 정보라
 *     HR이 원본을 열기 전에 묻는다
 * @param showsName 원본에 지원자 이름이 있다. 이력서에 쓰는 게 자연스러워 묻지 않고 안내만 한다
 */
public record OriginalWarning(DocumentType type, List<String> kinds, boolean showsName) {
}
