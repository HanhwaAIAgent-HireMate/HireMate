package com.hiremate.apply;

import java.util.List;

public record ApplicationPage(long total, List<ApplicationSummary> items) {
}
