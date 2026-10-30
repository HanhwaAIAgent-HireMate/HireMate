"""모델 설계서의 기계적인 규칙 위반을 코드가 고친다. 검사(check) 전에 한다.

모델에게 다시 쓰게 하면 하나를 고치며 다른 곳을 깨기 쉽다. 그릴 값이 정해진 부분(영역 점수 표, 관점 묶음,
빈 칸이 있는 막대, 같은 자료를 다시 그린 부품, 섹션당 부품 수)은 코드가 고치고, 문장 문제만 모델에게 돌려준다.
모델이 쓴 문장 · 근거는 바꾸지 않는다.
"""

import logging

from hiremate_ai.agents.generation.report.bundle import ReportBundle, ReportKind
from hiremate_ai.agents.generation.report.check import (
    DATA_FIELDS,
    MAX_SECTION_BLOCKS,
    MAX_SECTIONS,
    rings_problems,
)
from hiremate_ai.agents.generation.report.derive import ring_percent, score_view
from hiremate_ai.agents.generation.report.fallback import MAX_VIEWS, evidence_block, perspective_rings, score_rings
from hiremate_ai.agents.generation.report.spec import (
    VISUAL_TYPES,
    BarBlock,
    Block,
    EvidenceBlock,
    RadarBlock,
    ReportSpec,
    RingsBlock,
    RingView,
    Section,
    StackedBlock,
)

logger = logging.getLogger(__name__)

_PERSPECTIVE_PROBLEMS = ("관점 도넛", "관점 '", "항목 하나짜리")
OVERVIEW_TAKEAWAY = "영역 점수와 관점별 충족 항목 수예요."
"""코드가 표를 넣으려고 새로 둔 섹션의 읽을 점."""
EVIDENCE_TAKEAWAY = "대상끼리 판정이 갈린 항목의 근거예요."
"""코드가 넣은 근거 섹션의 읽을 점."""


def repair(spec: ReportSpec, bundle: ReportBundle, *, group_by_code: bool = True) -> ReportSpec:
    """고친 설계서. 고칠 것이 없으면 같은 내용이다.

    group_by_code가 false면 모델이 관점을 묶지 않았을 때 코드가 대신 묶지 않는다. 관점 이름은 항목 내용을 보고
    지어야 하므로, 다시 쓸 기회가 남았으면 모델에게 돌려준다.
    """
    sections = [
        section.model_copy(update={"blocks": _complete_rows(section.blocks, bundle)}) for section in spec.sections
    ]
    if bundle.kind is ReportKind.COMPARE and not bundle.brief:
        sections = _compare_rings(sections, bundle, spec.perspectives, group_by_code=group_by_code)
    sections = _without_repeats(sections)
    sections = [section for section in sections if section.blocks]
    if bundle.kind is ReportKind.COMPARE and not bundle.brief and group_by_code:
        sections = _with_evidence(sections, bundle)
    return spec.model_copy(update={"sections": sections})


def _with_evidence(sections: list[Section], bundle: ReportBundle) -> list[Section]:
    """근거 부품이 없으면 마지막 시도에서 코드가 고른 근거 섹션을 맨 뒤에 둔다. 판단 문장은 쓰지 않는다."""
    if any(isinstance(block, EvidenceBlock) for section in sections for block in section.blocks):
        return sections
    block = evidence_block(bundle, bundle.targets)
    if block is None or len(sections) >= MAX_SECTIONS:
        return sections
    logger.info("근거 섹션을 코드가 넣는다")
    return [*sections, Section(title="지원자별 근거", takeaway=EVIDENCE_TAKEAWAY, blocks=[block])]


def _complete_rows(blocks: list[Block], bundle: ReportBundle) -> list[Block]:
    """막대 · 쌓은 막대 · 레이더에서 값이 빈(보류) 지원자가 있는 key를 뺀다. 남은 key가 모자라면 부품을 뺀다."""
    kept: list[Block] = []
    for block in blocks:
        if isinstance(block, BarBlock | StackedBlock | RadarBlock):
            keys = [key for key in block.keys if _everyone_has(bundle, key, block.applicants)]
            least = 1 if isinstance(block, BarBlock) else 2 if isinstance(block, StackedBlock) else 3
            if len(keys) < least:
                continue
            block = block.model_copy(update={"keys": keys})
        kept.append(block)
    return kept


def _everyone_has(bundle: ReportBundle, key: str, applicants: list[str]) -> bool:
    have = {fact.applicant for fact in bundle.facts if fact.key == key}
    return all(number in have for number in applicants)


def _named_perspectives(views: list[RingView], bundle: ReportBundle) -> RingsBlock | None:
    """모델이 이름 붙여 묶은 관점으로 만든 관점 표. 규칙에 맞지 않으면 None이다."""
    if not views:
        return None
    block = RingsBlock(
        title="관점별 항목 충족",
        caption="관점마다 충족한 항목 수를 칸으로 채웠어요.",
        views=views,
        applicants=bundle.targets,
    )
    if not _drawable(block, bundle) or any(
        p.startswith(_PERSPECTIVE_PROBLEMS) for p in rings_problems([block], bundle)
    ):
        return None
    return block


def _compare_rings(
    sections: list[Section], bundle: ReportBundle, spec_perspectives: list[RingView], *, group_by_code: bool
) -> list[Section]:
    """비교 리포트의 영역 점수 표와 관점 표. 없거나 관점 묶음이 규칙에 맞지 않으면 코드가 만든 것으로 바꾼다."""
    rings = [block for section in sections for block in section.blocks if isinstance(block, RingsBlock)]
    found = rings_problems(rings, bundle)
    missing_scores = any("영역 점수" in problem for problem in found)
    bad_perspectives = any(problem.startswith(_PERSPECTIVE_PROBLEMS) for problem in found) or any(
        _is_perspective(block, bundle) and not _drawable(block, bundle) for block in rings
    )
    if not missing_scores and not bad_perspectives:
        return sections
    added: list[Block] = []
    if missing_scores and (scores := score_rings(bundle, bundle.targets)) is not None:
        added.append(scores)
    named = _named_perspectives(spec_perspectives, bundle) if bad_perspectives else None
    if named is None and bad_perspectives and group_by_code:
        # 모델이 관점을 묶지 않았고 다시 쓸 기회도 없으면 코드가 묶는다. 지원자 정보 없이 묶음 모양만 남긴다
        logger.info(
            "관점 표를 코드가 묶는다: %s | 모델 관점 %s",
            " | ".join(p for p in found if p.startswith(_PERSPECTIVE_PROBLEMS)),
            [
                [len(view.keys) for view in view_block.views]
                for view_block in rings
                if _is_perspective(view_block, bundle)
            ],
        )
        named = perspective_rings(bundle, bundle.targets)
    if named is not None:
        # 규칙에 맞지 않는 관점 표는 빼고 바꾼다
        sections = [
            section.model_copy(update={"blocks": [b for b in section.blocks if not _is_perspective(b, bundle)]})
            for section in sections
        ]
        added.append(named)
    if not added:
        return sections
    overview = next((index for index, section in enumerate(sections) if section.area is None), None)
    if overview is None:
        # 영역 섹션에는 다른 영역 값을 넣지 않으므로, 맨 앞에 한눈에 보기 섹션을 새로 둔다
        head = Section(title="한눈에 보기", takeaway=OVERVIEW_TAKEAWAY, blocks=added)
        return [head, *sections][:MAX_SECTIONS]
    # 영역 점수 표, 관점 표, 나머지 순으로 두고 넘치는 부품은 뒤에서부터 뺀다. 표 두 개가 이 리포트의 맨 위 그림이다
    first = sections[overview]
    merged = [*added, *first.blocks]
    tables = [b for b in merged if isinstance(b, RingsBlock)]
    ordered = sorted(tables, key=lambda b: _is_perspective(b, bundle)) + [
        b for b in merged if not isinstance(b, RingsBlock)
    ]
    blocks = ordered[:MAX_SECTION_BLOCKS]
    return [*sections[:overview], first.model_copy(update={"blocks": blocks}), *sections[overview + 1 :]]


def _is_perspective(block: Block, bundle: ReportBundle) -> bool:
    return isinstance(block, RingsBlock) and not all(score_view(bundle, view.keys) for view in block.views)


def _drawable(block: RingsBlock, bundle: ReportBundle) -> bool:
    """관점 표를 그릴 수 있는가. 관점 2~6개이고 관점마다 모든 지원자의 판정이 있어야 한다."""
    return 2 <= len(block.views) <= MAX_VIEWS and all(
        ring_percent(bundle, view.keys, number) is not None for view in block.views for number in block.applicants
    )


def _without_repeats(sections: list[Section]) -> list[Section]:
    """같은 자료를 다시 그린 부품과 섹션당 넘치는 부품을 뺀다."""
    seen: set[str] = set()
    fixed = []
    for section in sections:
        blocks = []
        for block in section.blocks:
            if block.type in VISUAL_TYPES:
                signature = block.model_dump_json(include=DATA_FIELDS)
                if signature in seen:
                    continue
                seen.add(signature)
            blocks.append(block)
        fixed.append(section.model_copy(update={"blocks": blocks[:MAX_SECTION_BLOCKS]}))
    return fixed
