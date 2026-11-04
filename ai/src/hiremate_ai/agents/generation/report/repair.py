"""모델 설계서의 기계적인 규칙 위반을 코드가 고친다. 검사(check) 전에 한다.

모델에게 다시 쓰게 하면 하나를 고치며 다른 곳을 깨기 쉽다. 그릴 값이 정해진 부분(값 key의 *, 영역 점수 표,
관점 묶음, 항목 하나짜리 관점 수, 빈 칸이 있는 막대, 그릴 자료가 맞지 않는 부품, 같은 자료를 다시 그린 부품,
섹션당 부품 수, 근거 부품에서 빠진 비교 대상, 문장 속 판정 코드)은 코드가 고치고,
문장 문제만 모델에게 돌려준다. 모델이 쓴 문장 · 근거는 판정 코드를 화면 말로 바꾸는 것 말고는 바꾸지 않는다.
다만 마지막 시도에서도 읽을 점을 그림
설명으로 쓰면, 기본 구성으로 떨어지지 않게 그 한 문장만 코드가 판정에서 읽은 사실로 바꾼다.
"""

import logging
import re

from hiremate_ai.agents.generation.report.bundle import ReportBundle, ReportKind, Strength
from hiremate_ai.agents.generation.report.check import (
    DATA_FIELDS,
    DESCRIBING,
    MAX_KPI_METRICS,
    MAX_SECTION_BLOCKS,
    MAX_SECTIONS,
    MAX_SINGLE_VIEWS,
    block_data_problems,
    rings_problems,
)
from hiremate_ai.agents.generation.report.derive import ring_percent, score_view, split_keys
from hiremate_ai.agents.generation.report.fallback import (
    MAX_SPLITS,
    MAX_VIEWS,
    code_split,
    evidence_block,
    final_consonant,
    perspective_rings,
    score_rings,
)
from hiremate_ai.agents.generation.report.spec import (
    VISUAL_TYPES,
    BarBlock,
    Block,
    EvidenceBlock,
    EvidenceItem,
    KpiBlock,
    RadarBlock,
    ReportSpec,
    RingsBlock,
    RingView,
    Section,
    Split,
    StackedBlock,
    TallyBlock,
    TextBlock,
)

logger = logging.getLogger(__name__)

_PERSPECTIVE_PROBLEMS = ("관점 도넛", "관점 '", "항목 하나짜리")
OVERVIEW_TAKEAWAY = "영역 점수와 관점별 충족 항목 수예요."
"""코드가 표를 넣으려고 새로 둔 섹션의 읽을 점."""
EVIDENCE_TAKEAWAY = "대상끼리 판정이 갈린 항목의 근거예요."
"""코드가 넣은 근거 섹션의 읽을 점."""


def repair(
    spec: ReportSpec, bundle: ReportBundle, *, group_by_code: bool = True, notes: list[str] | None = None
) -> ReportSpec:
    """고친 설계서. 고칠 것이 없으면 같은 내용이다.

    group_by_code가 false면 모델이 관점을 묶지 않았을 때 코드가 대신 묶지 않는다. 관점 이름은 항목 내용을 보고
    지어야 하므로, 다시 쓸 기회가 남았으면 모델에게 돌려준다.
    notes를 주면 코드가 고친 것을 화면의 AI 작업 과정에 보일 한 줄로 더한다.
    """
    done = notes if notes is not None else []

    def step(before: list[Section], after: list[Section], note: str) -> list[Section]:
        if after != before:
            done.append(note)
        return after

    sections = step(spec.sections, _expand_wildcards(spec.sections, bundle), "값 key의 *를 항목으로 폄")
    sections = [section.model_copy(update={"blocks": _complete_rows(section.blocks, bundle)}) for section in sections]
    sections = step(sections, _merged_singles(sections), "항목 하나짜리 그래프를 하나로 합침")
    drawable = _without_undrawable(sections, bundle)
    if dropped := sum(len(s.blocks) for s in sections) - sum(len(s.blocks) for s in drawable):
        done.append(f"그릴 수 없는 그래프 {dropped}개를 뺌")
    sections = drawable
    perspectives = spec.perspectives
    compare = bundle.kind is ReportKind.COMPARE and not bundle.brief
    if compare:
        expanded = _expand_views(perspectives, bundle)
        perspectives = _pair_singles(expanded)
        paired = _paired_rings(sections, bundle)
        if perspectives != expanded or paired != sections:
            done.append("항목 하나짜리 관점을 둘씩 묶음")
        sections = paired
        sections = step(
            sections,
            _compare_rings(sections, bundle, perspectives, group_by_code=group_by_code),
            "관점 표를 규칙에 맞게 다시 묶음",
        )
    sections = _without_repeats(sections)
    sections = [section for section in sections if section.blocks]
    sections = step(sections, _quantified_first(sections, bundle), "정량 근거를 근거 맨 앞으로 옮김")
    splits = _valid_splits(spec.splits, bundle) if compare else []
    if compare:
        sections = step(sections, _cite_everyone(sections, bundle), "근거에서 빠진 지원자의 근거를 채움")
        if group_by_code:
            sections = step(sections, _with_evidence(sections, bundle), "근거 섹션을 더함")
            sections = step(sections, _read_takeaways(sections, bundle), "그림 설명 문장을 판정 사실로 바꿈")
            written = {split.key for split in splits}
            added = [code_split(bundle, key) for key in split_keys(bundle) if key not in written]
            if added := added[: max(0, MAX_SPLITS - len(splits))]:
                done.append(f"갈린 이유 {len(added)}건을 판정으로 채움")
                splits = [*splits, *added]
    fixed = spec.model_copy(update={"sections": sections, "splits": splits, "perspectives": perspectives})
    plain = _plain_codes(fixed)
    if plain != fixed:
        done.append("판정 코드를 화면 말로 바꿈")
    return plain


_CODE_WORDS = {
    "NOT_RECOMMENDED": "추천 밖",
    "RECOMMENDED": "AI 추천",
    "NOT_CONFIRMED": "미확인",
    "UNCONFIRMED": "미확인",
    "CONFIRMED": "확인됨",
    "CONFLICT": "상충",
    "NOT_MET": "미충족",
    "PARTIAL": "부분 충족",
    "UNKNOWN": "보류",
    "MET": "충족",
    "PASS": "합격",
    "FAIL": "불합격",
}
"""판정 코드와 화면 말 (frontend report/palette.ts의 STATUS · WORDS와 같은 말). 긴 코드부터 바꾼다."""
_PARTICLES = {
    "이에요": ("이에요", "예요"),
    "예요": ("이에요", "예요"),
    "으로": ("으로", "로"),
    "은": ("은", "는"),
    "는": ("은", "는"),
    "이": ("이", "가"),
    "가": ("이", "가"),
    "을": ("을", "를"),
    "를": ("을", "를"),
    "과": ("과", "와"),
    "와": ("과", "와"),
    "로": ("으로", "로"),
}
"""코드 바로 뒤의 조사. 바꾼 말의 받침에 맞춰 (받침 있을 때, 없을 때) 중 하나로 고친다."""
_CODE = re.compile(r"(?<![A-Za-z_])(" + "|".join(_CODE_WORDS) + r")(?![A-Za-z_])(" + "|".join(_PARTICLES) + r")?")


def _plain(text: str) -> str:
    def word(match: re.Match[str]) -> str:
        plain, particle = _CODE_WORDS[match.group(1)], match.group(2)
        if not particle:
            return plain
        consonant = final_consonant(plain)
        with_final, without = _PARTICLES[particle]
        # ㄹ 받침 뒤의 '으로'는 '로'다 (예: 보류로)
        fits = with_final if consonant and not (particle in ("으로", "로") and consonant == 8) else without
        return plain + fits

    return _CODE.sub(word, text)


def _plain_codes(spec: ReportSpec) -> ReportSpec:
    """문장 속 판정 코드(PASS, MET …)를 화면 말로 바꾼다. 다시 쓰게 하면 다른 곳을 깨기 쉬워 코드가 바꾼다.
    제목 · 요약 · 읽을 점 · 그림 설명 · 글 · 근거 · 갈린 이유만 바꾸고,
    그릴 값을 가리키는 칸(key, 그룹 값)은 그대로 둔다."""

    def block(item: Block) -> Block:
        update: dict[str, object] = {"title": _plain(item.title)}
        if isinstance(caption := getattr(item, "caption", None), str):
            update["caption"] = _plain(caption)
        if isinstance(item, TextBlock):
            update["text"] = _plain(item.text)
        if isinstance(item, EvidenceBlock):
            update["items"] = [
                line.model_copy(update={"text": _plain(line.text), "keywords": [_plain(k) for k in line.keywords]})
                for line in item.items
            ]
        return item.model_copy(update=update)

    sections = [
        section.model_copy(
            update={
                "title": _plain(section.title),
                "takeaway": _plain(section.takeaway),
                "blocks": [block(item) for item in section.blocks],
            }
        )
        for section in spec.sections
    ]
    splits = [split.model_copy(update={"text": _plain(split.text)}) for split in spec.splits]
    return spec.model_copy(
        update={"title": _plain(spec.title), "summary": _plain(spec.summary), "sections": sections, "splits": splits}
    )


def _without_undrawable(sections: list[Section], bundle: ReportBundle) -> list[Section]:
    """그릴 자료가 맞지 않는 시각화 부품을 뺀다 (숫자가 아닌 값의 분포, key 하나짜리 비율 막대, 묶음이 섞인 도넛 등).
    섹션에 부품이 하나뿐이면 빼지 않고 검사가 다시 쓰게 한다. 관점 · 영역 점수 표는 _compare_rings가 맡는다.
    영역 섹션이 아닌데 부품을 모두 그릴 수 없으면 섹션째 뺀다 (영역 섹션은 검사가 빠졌다고 알리므로 둔다).
    """
    fixed = []
    for section in sections:
        kept = [
            block
            for block in section.blocks
            if block.type not in VISUAL_TYPES or isinstance(block, RingsBlock) or not block_data_problems(block, bundle)
        ]
        if not kept and section.area is None and len(sections) > 1:
            logger.info("그릴 수 있는 부품이 없는 섹션을 코드가 뺀다: %s", ", ".join(b.type for b in section.blocks))
            continue
        if not kept or len(kept) == len(section.blocks):
            kept = section.blocks
        elif dropped := [b.type for b in section.blocks if b not in kept]:
            logger.info("그릴 수 없는 부품을 코드가 뺀다: %s", ", ".join(dropped))
        fixed.append(section.model_copy(update={"blocks": kept}))
    return fixed


def _merged_singles(sections: list[Section]) -> list[Section]:
    """한 섹션에서 key 하나짜리 비율 막대(같은 by)와 지표 하나짜리 kpi를 하나로 합친다.
    모델이 전형마다 부품을 하나씩 두다 모두 '2개 이상'에 걸리는 일이 있다. 제목 · 설명은 첫 부품 것을 쓴다."""
    fixed = []
    for section in sections:
        blocks: list[Block] = []
        for block in section.blocks:
            last = blocks[-1] if blocks else None
            if (
                isinstance(block, TallyBlock)
                and isinstance(last, TallyBlock)
                and last.by == block.by
                and last.applicants == block.applicants
                and (len(last.keys) < 2 or len(block.keys) < 2)
            ):
                blocks[-1] = last.model_copy(update={"keys": list(dict.fromkeys([*last.keys, *block.keys]))})
            elif (
                isinstance(block, KpiBlock)
                and isinstance(last, KpiBlock)
                and (len(last.metrics) < 2 or len(block.metrics) < 2)
            ):
                blocks[-1] = last.model_copy(
                    update={"metrics": list(dict.fromkeys([*last.metrics, *block.metrics]))[:MAX_KPI_METRICS]}
                )
            else:
                blocks.append(block)
        fixed.append(section.model_copy(update={"blocks": blocks}))
    return fixed


def _known_keys(bundle: ReportBundle) -> list[str]:
    """묶음의 값 key. 영역 항목 순서를 먼저 따른다."""
    return list(dict.fromkeys([*(key for area in bundle.areas for key in area.keys), *(f.key for f in bundle.facts)]))


def _expand(keys: list[str], known: list[str]) -> list[str]:
    """끝에 *를 붙인 key를 그 앞이 같은 key 전부로 편다. 맞는 key가 없으면 그대로 두어 검사가 알린다."""
    expanded: list[str] = []
    for key in keys:
        matched = [k for k in known if k.startswith(key[:-1])] if key.endswith("*") else []
        expanded += [k for k in matched or [key] if k not in expanded]
    return expanded


def _expand_views(views: list[RingView], bundle: ReportBundle) -> list[RingView]:
    known = _known_keys(bundle)
    return [view.model_copy(update={"keys": _expand(view.keys, known)}) for view in views]


def _expand_wildcards(sections: list[Section], bundle: ReportBundle) -> list[Section]:
    """부품 keys의 *를 묶음의 실제 key로 편다. 자료를 읽는 도구가 *를 받으므로 모델이 부품에도 그대로 쓴다."""

    def expand(block: Block) -> Block:
        if isinstance(block, RingsBlock):
            return block.model_copy(update={"views": _expand_views(block.views, bundle)})
        keys = getattr(block, "keys", None)
        if isinstance(keys, list) and any(key.endswith("*") for key in keys):
            return block.model_copy(update={"keys": _expand(keys, _known_keys(bundle))})
        return block

    return [section.model_copy(update={"blocks": [expand(b) for b in section.blocks]}) for section in sections]


def _pair_singles(views: list[RingView]) -> list[RingView]:
    """항목 하나짜리 관점이 MAX_SINGLE_VIEWS개를 넘으면 차례로 둘씩 합친다. 이름은 모델이 지은 두 이름을 잇는다.

    한 항목이면 도넛이 0% 아니면 100%라, 모델에게 다시 묶게 하는 대신 코드가 합친다.
    개수가 홀수면 맨 앞 하나는 그대로 둔다.
    """
    singles = [index for index, view in enumerate(views) if len(view.keys) == 1]
    if len(singles) <= MAX_SINGLE_VIEWS:
        return views
    paired = singles[len(singles) % 2 :]
    merged = list(views)
    for first, second in zip(paired[::2], paired[1::2], strict=True):
        a, b = views[first], views[second]
        merged[first] = RingView(label=f"{a.label} · {b.label}", keys=list(dict.fromkeys([*a.keys, *b.keys])))
    drop = set(paired[1::2])
    return [view for index, view in enumerate(merged) if index not in drop]


def _paired_rings(sections: list[Section], bundle: ReportBundle) -> list[Section]:
    """설계서에 넣은 관점 표의 항목 하나짜리 관점을 둘씩 합친다."""

    def pair(block: Block) -> Block:
        if isinstance(block, RingsBlock) and _is_perspective(block, bundle):
            return block.model_copy(update={"views": _pair_singles(block.views)})
        return block

    return [section.model_copy(update={"blocks": [pair(b) for b in section.blocks]}) for section in sections]


def _valid_splits(splits: list[Split], bundle: ReportBundle) -> list[Split]:
    """판정이 갈린 항목이 아니거나 비교 대상 밖 근거를 든 갈린 이유는 뺀다. 같은 항목은 처음 것만 둔다."""
    keys = set(split_keys(bundle))
    owners = {item.id: item.applicant for item in bundle.evidence}
    kept: list[Split] = []
    for split in splits:
        if split.key not in keys or any(split.key == other.key for other in kept):
            continue
        evidence = [id_ for id_ in split.evidence if owners.get(id_) in bundle.targets]
        kept.append(split.model_copy(update={"evidence": evidence}))
    return kept[:MAX_SPLITS]


def _quantified_first(sections: list[Section], bundle: ReportBundle) -> list[Section]:
    """근거 항목마다 그 지원자의 정량 근거(성과를 숫자로 적은 원문)를 맨 앞에 둔다. 모델이 빠뜨렸으면 코드가 더한다.

    정량 근거가 서술 근거보다 강하다는 위계를 모델에게만 맡기지 않는다.
    근거가 없다고 쓴 항목(근거 id 없음)은 그대로 둔다.
    """
    quantified: dict[str, list[str]] = {}
    for item in bundle.evidence:
        if item.strength is Strength.QUANT:
            quantified.setdefault(item.applicant, []).append(item.id)
    if not quantified:
        return sections

    def reorder(item: EvidenceItem) -> EvidenceItem:
        mine = quantified.get(item.applicant, [])
        if not item.evidence or not mine:
            return item
        ordered = [*mine, *(evidence for evidence in item.evidence if evidence not in mine)]
        return item if ordered == item.evidence else item.model_copy(update={"evidence": ordered})

    fixed = []
    for section in sections:
        blocks: list[Block] = [
            block.model_copy(update={"items": [reorder(item) for item in block.items]})
            if isinstance(block, EvidenceBlock)
            else block
            for block in section.blocks
        ]
        fixed.append(section.model_copy(update={"blocks": blocks}))
    return fixed


def _cite_everyone(sections: list[Section], bundle: ReportBundle) -> list[Section]:
    """근거 부품에서 빠진 비교 대상의 근거를 코드가 골라 첫 근거 부품에 더한다. 키워드는 항목 이름, 근거는 id만 쓴다."""
    blocks = [block for section in sections for block in section.blocks if isinstance(block, EvidenceBlock)]
    if not blocks:
        return sections
    cited = {item.applicant for block in blocks for item in block.items}
    have = {item.applicant for item in bundle.evidence}
    missing = [number for number in bundle.targets if number in have and number not in cited]
    # 판정이 갈린 항목은 비교 대상 전체를 보고 고르므로 전체로 만들고 빠진 사람 것만 쓴다
    chosen = evidence_block(bundle, bundle.targets) if missing else None
    added = [item for item in (chosen.items if chosen else []) if item.applicant in missing]
    if not added:
        return sections
    logger.info("근거 부품에 빠진 비교 대상의 근거를 코드가 더한다: %d명", len(added))
    first = blocks[0]
    fixed = first.model_copy(update={"items": [*first.items, *added]})
    return [
        section.model_copy(update={"blocks": [fixed if block is first else block for block in section.blocks]})
        for section in sections
    ]


def _read_takeaways(sections: list[Section], bundle: ReportBundle) -> list[Section]:
    """그림 설명으로 쓴 읽을 점을 마지막 시도에서 코드가 읽은 사실로 바꾼다. 영역 섹션은 판정이 갈린 항목을 적는다."""
    fixed = []
    for section in sections:
        if DESCRIBING.search(section.takeaway):
            takeaway = _area_takeaway(section, bundle) or (
                EVIDENCE_TAKEAWAY
                if any(isinstance(block, EvidenceBlock) for block in section.blocks)
                else OVERVIEW_TAKEAWAY
            )
            logger.info("그림 설명으로 쓴 읽을 점을 코드가 바꾼다")
            section = section.model_copy(update={"takeaway": takeaway})
        fixed.append(section)
    return fixed


def _area_takeaway(section: Section, bundle: ReportBundle) -> str | None:
    """영역 섹션의 읽을 점. 비교 대상끼리 판정이 갈린 항목 코드를 두 개까지 적는다. 숫자는 쓰지 않는다."""
    area = next((area for area in bundle.areas if area.id == section.area), None)
    if area is None:
        return None
    verdicts = {(fact.applicant, fact.key): fact.value for fact in bundle.facts}
    split = [
        key.rsplit(".", 1)[-1]
        for key in area.keys
        if len({verdicts.get((number, key)) for number in bundle.targets} - {None}) > 1
    ]
    if not split:
        return f"{area.label} 항목은 비교 대상의 판정이 모두 같아요."
    more = " 등" if len(split) > 2 else ""
    return f"{area.label} 항목 중 {' · '.join(split[:2])}{more}에서 판정이 갈렸어요."


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
