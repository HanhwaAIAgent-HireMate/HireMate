package com.hiremate.company;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * 로고에서 고른 메일 대표 색. 저장하지 않고 설정 화면의 색 칸만 채운다. HR이 미리보기를 보고 저장한다.
 *
 * @param color 대표 색 (#rrggbb). 회사 색으로 볼 색이 없으면 null
 * @param candidates 그림에서 많이 쓰인 색. 많은 순서로 최대 5개
 */
public record MailColorSuggestion(@Schema(nullable = true) String color, List<ColorCandidate> candidates) {

    /**
     * 그림에서 찾은 색 하나.
     *
     * @param share 그림의 불투명한 부분에서 이 색이 차지하는 비율 (0~1)
     */
    public record ColorCandidate(String color, double share) {
    }
}
