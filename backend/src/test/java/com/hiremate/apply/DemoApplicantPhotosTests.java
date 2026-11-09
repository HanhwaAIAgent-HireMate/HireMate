package com.hiremate.apply;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class DemoApplicantPhotosTests {

    @Test
    void enablesOnlySpecifiedRecruitments() {
        UUID allowed = UUID.randomUUID();
        DemoApplicantPhotos photos = new DemoApplicantPhotos(allowed.toString());
        assertThat(photos.enabled(allowed)).isTrue();
        assertThat(photos.enabled(UUID.randomUUID())).isFalse();
        assertThat(new DemoApplicantPhotos("").enabled(allowed)).isFalse();
    }

    @Test
    void choosesStablePhotoFromTheMatchingTestNameGroup() {
        UUID id = UUID.randomUUID();
        assertThat(DemoApplicantPhotos.index(id, "박지훈") % 2).isZero();
        assertThat(DemoApplicantPhotos.index(id, "김서연") % 2).isEqualTo(1);
        assertThat(DemoApplicantPhotos.index(id, "박지훈"))
                .isEqualTo(DemoApplicantPhotos.index(id, "박지훈"));
        assertThat(DemoApplicantPhotos.index(id, "홍지안")).isBetween(0, 7);
    }
}
