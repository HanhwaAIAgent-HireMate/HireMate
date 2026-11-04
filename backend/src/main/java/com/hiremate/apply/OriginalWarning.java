package com.hiremate.apply;

import com.hiremate.posting.DocumentType;
import java.util.List;

/**
 * 원본 PDF를 열면 블라인드로 가린 정보가 보이는 서류. kinds는 원본에 그대로 있는 정보다 (예: "출신 학교", "학점").
 * 지원자가 블라인드 원칙과 달리 적은 정보라, HR이 원본을 열기 전에 알린다.
 */
public record OriginalWarning(DocumentType type, List<String> kinds) {
}
