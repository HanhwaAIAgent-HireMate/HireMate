package com.hiremate.posting.api;

import com.hiremate.recruit.StageDraft;
import com.hiremate.recruit.StageIcon;
import com.hiremate.recruit.StageType;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * HR이 공고 작성 화면에서 직접 정한 전형 절차. 순서대로 1개에서 10개까지다.
 *
 * @param stages 전형 이름과 종류. 이름은 기업이 부르는 그대로 쓴다
 */
public record StagesRequest(@NotNull @Size(min = 1, max = 10) List<@NotNull @Valid StageItem> stages) {

    public List<StageDraft> toDrafts() {
        return stages.stream().map(stage -> new StageDraft(stage.name().strip(), stage.type(), stage.icon())).toList();
    }

    public record StageItem(@NotBlank @Size(max = 50) String name, @NotNull StageType type,
            @Schema(nullable = true, requiredMode = Schema.RequiredMode.NOT_REQUIRED) StageIcon icon) {
    }
}
