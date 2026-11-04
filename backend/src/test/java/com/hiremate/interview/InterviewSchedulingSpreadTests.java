package com.hiremate.interview;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Arrays;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** 칸마다 몇 명을 넣을지 정하는 계산만 DB 없이 검사한다. */
class InterviewSchedulingSpreadTests {

    /** 지원자 없는 칸을 size개 만든다 */
    private static int[] empty(int size) {
        return new int[size];
    }

    @Test
    @DisplayName("칸이 충분하면 앞 칸부터 한 명씩 넣고 남은 칸은 비운다")
    void onePerSlotWhenEnough() {
        assertThat(InterviewScheduling.spread(empty(10), 8)).containsExactly(1, 1, 1, 1, 1, 1, 1, 1, 0, 0);
    }

    @Test
    @DisplayName("칸이 모자라면 고르게 나누고 남는 사람은 앞 칸에 더 넣는다")
    void remainderGoesToEarlierSlots() {
        assertThat(InterviewScheduling.spread(empty(10), 12)).containsExactly(2, 2, 1, 1, 1, 1, 1, 1, 1, 1);
        assertThat(InterviewScheduling.spread(empty(10), 53)).containsExactly(6, 6, 6, 5, 5, 5, 5, 5, 5, 5);
    }

    @Test
    @DisplayName("하루 아홉 칸에 45명이면 칸마다 5명이다")
    void fortyFiveInOneDay() {
        int[] expected = new int[9];
        Arrays.fill(expected, 5);
        assertThat(InterviewScheduling.spread(empty(9), 45)).containsExactly(expected);
    }

    @Test
    @DisplayName("이미 사람이 있는 칸은 그 인원까지 세어 고르게 맞춘다")
    void countsPeopleAlreadyInSlot() {
        assertThat(InterviewScheduling.spread(new int[] {2, 0, 0}, 2)).containsExactly(0, 1, 1);
        assertThat(InterviewScheduling.spread(new int[] {2, 0, 0}, 5)).containsExactly(1, 2, 2);
    }
}
