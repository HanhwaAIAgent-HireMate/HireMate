package com.hiremate.screening;

import java.util.List;

public record CandidatePage(long total, List<CandidateRow> items) {
}
