"""기본 구성. 모델 설계서가 두 번 모두 검사를 통과하지 못하면 코드가 묶음만으로 만든다.

기본 구성도 모델 설계서와 같은 섹션(한눈에 보기 → 영역마다 한 섹션)과 시각화를 갖추고,
요약은 자동 요약을 만들지 못했다는 안내다.
"""

import re
from collections import Counter

from hiremate_ai.agents.generation.report.bundle import Area, Evidence, Fact, ReportBundle, ReportKind, Strength
from hiremate_ai.agents.generation.report.check import MAX_SECTION_BLOCKS, MIN_PERSPECTIVES
from hiremate_ai.agents.generation.report.derive import HAVE, POSITIVE, drawable, score_view, split_keys
from hiremate_ai.agents.generation.report.enrich import criterion_key, stage_prefix
from hiremate_ai.agents.generation.report.spec import (
    BarBlock,
    Block,
    CompositionBlock,
    CompositionRow,
    CrossBlock,
    DistributionBlock,
    DonutBlock,
    EvidenceBlock,
    EvidenceItem,
    KpiBlock,
    MatrixBlock,
    ReportSpec,
    RingsBlock,
    RingView,
    Section,
    ShareBlock,
    Split,
    StackedBlock,
    TableBlock,
    TallyBlock,
)

NO_SUMMARY = "자동 요약을 만들지 못했어요. 아래 지표와 표는 기록 그대로예요."
NO_TAKEAWAY = "기록 그대로예요."
MAX_MATRIX_KEYS = 8
MAX_REFERENCE = 2
MAX_SHARE_KEYS = 8
MAX_SLICES = 5
MAX_RING_ITEMS = 12
"""관점 도넛 대신 쓰는 항목 수. 둘씩 묶어 관점 6개까지다."""
MAX_FINALISTS = 10
FINAL_METRICS = ("m-applicants", "m-finalists", "m-final-rate")
"""최종 리포트 한눈에 보기 지표. 뒤에 전형별 합격 지표를 붙인다."""
_ITEM_CODE = re.compile(r"[A-Z]{1,3}-\d+")
MAX_VIEW_NAME = 14
MAX_VIEWS = 6
MAX_SPLITS = 6
"""비교 리포트의 '판정이 갈린 이유' 수."""
_VERDICT_WORDS = {"MET": "충족", "PARTIAL": "부분 충족", "NOT_MET": "미충족", "UNKNOWN": "확인 필요"}
MAX_EVIDENCE = 3
"""비교 리포트 근거에서 대상마다 고르는 근거 수."""
_DANGLING = {"·", "또는", "및", "등", "와", "과"}
"""관점 표의 관점 수 상한 (check의 관점 2~6개)."""
"""관점 이름에 쓰는 항목 이름 길이. 두세 항목을 ' · '로 이어 표 한 칸에 들어가게 한다."""


def fallback_spec(bundle: ReportBundle) -> ReportSpec:
    compare = bundle.kind is ReportKind.COMPARE
    people = bundle.targets if compare else [a.number for a in bundle.applicants]
    # 최종 리포트는 모든 전형이 범위다
    final = bundle.kind is ReportKind.FINAL
    current = list(bundle.facts) if final else [fact for fact in bundle.facts if fact.stage_id == bundle.stage_id]
    numeric = _common_keys(current, people, numeric=True)
    verdicts = _common_keys(current, people, numeric=False)
    sections = []
    if overview := _overview(bundle, people, numeric, current):
        sections.append(Section(title="한눈에 보기", takeaway=NO_TAKEAWAY, blocks=overview[:MAX_SECTION_BLOCKS]))
    if bundle.brief:
        return ReportSpec(title=bundle.title, summary=NO_SUMMARY, sections=sections[:1])
    if not compare:
        drawn = _drawable_blocks(bundle)
        for start in range(0, len(drawn), MAX_SECTION_BLOCKS):
            sections.append(
                Section(title="전형 기록", takeaway=NO_TAKEAWAY, blocks=drawn[start : start + MAX_SECTION_BLOCKS])
            )
    for area in bundle.areas:
        if blocks := _area_blocks(bundle, area, people, numeric, verdicts, current):
            sections.append(Section(title=area.label, area=area.id, takeaway=NO_TAKEAWAY, blocks=blocks))
    if compare and (evidence := evidence_block(bundle, people)) is not None:
        sections.append(Section(title="지원자별 근거", takeaway=NO_TAKEAWAY, blocks=[evidence]))
    if final and (finalists := _finalists(bundle)):
        keys = [area.score_key for area in bundle.areas if area.score_key] + _decisions(bundle)
        sections.append(
            Section(
                title="최종 합격자",
                takeaway=NO_TAKEAWAY,
                blocks=[
                    TableBlock(
                        title="최종 합격자 기록",
                        caption="최종 합격자의 전형별 점수와 결정이에요.",
                        keys=keys,
                        applicants=finalists[:MAX_FINALISTS],
                    )
                ],
            )
        )
    if not bundle.areas and (numeric or verdicts):
        sections.append(
            Section(
                title="지원자별 점수와 판정",
                takeaway=NO_TAKEAWAY,
                blocks=[
                    TableBlock(
                        title="지원자별 점수와 판정",
                        caption="지원자마다 점수와 판정을 모았어요.",
                        keys=(numeric + verdicts)[:6],
                        applicants=people[:5],
                    )
                ],
            )
        )
    splits = [code_split(bundle, key) for key in split_keys(bundle)][:MAX_SPLITS] if compare else []
    return ReportSpec(title=bundle.title, summary=NO_SUMMARY, sections=sections, splits=splits)


def code_split(bundle: ReportBundle, key: str) -> Split:
    """판정이 갈린 항목 하나를 판정으로만 적는다. 모델이 이유를 쓰지 못했을 때 쓰고, 해석은 붙이지 않는다."""
    verdicts = {fact.applicant: fact.value for fact in bundle.facts if fact.key == key}
    groups: dict[str, list[str]] = {}
    for number in bundle.targets:
        if isinstance(value := verdicts.get(number), str):
            groups.setdefault(value, []).append(number)
    parts = [f"{' · '.join(numbers)} {_VERDICT_WORDS.get(value, value)}" for value, numbers in groups.items()]
    criterion = key.rsplit(".", 1)[-1]
    ids = {item.id for item in bundle.evidence}
    evidence = [id_ for number in bundle.targets if (id_ := f"e-{number}-{criterion}") in ids]
    return Split(key=key, text=f"판정이 갈렸어요 ({' · '.join(parts)}).", evidence=evidence)


def _overview(bundle: ReportBundle, people: list[str], numeric: list[str], current: list[Fact]) -> list[Block]:
    compare = bundle.kind is ReportKind.COMPARE
    blocks: list[Block] = []
    if bundle.kind is ReportKind.FINAL:
        ids = [m.id for m in bundle.metrics if m.id in FINAL_METRICS] + [
            m.id for m in bundle.metrics if m.id.endswith("-pass")
        ]
        blocks.append(KpiBlock(title="주요 지표", caption="지원부터 최종 합격까지의 인원이에요.", metrics=ids[:5]))
        if len(decisions := _decisions(bundle)) >= 2:
            blocks.append(
                TallyBlock(title="전형별 결정", caption="전형마다 합격 · 불합격 비율이에요.", keys=decisions, by="key")
            )
        return blocks
    if not compare and len(bundle.metrics) >= 2:
        blocks.append(
            KpiBlock(
                title="주요 지표", caption="전형 결과의 인원과 지표예요.", metrics=[m.id for m in bundle.metrics[:4]]
            )
        )
    scores = [area.score_key for area in bundle.areas if area.score_key in numeric]
    # 영역 점수 표는 점수가 빈(보류) 지원자를 '확인 필요'로 그리므로 모든 영역을 넣는다
    if compare and (scores_table := score_rings(bundle, people)) is not None:
        blocks.append(scores_table)
    if compare and (perspectives := perspective_rings(bundle, people)) is not None:
        blocks.append(perspectives)
    if compare and len(scores) >= 2:
        blocks.append(
            StackedBlock(
                title="영역별 점수로 본 총점", caption="영역 점수를 쌓은 총점이에요.", keys=scores, applicants=people
            )
        )
    elif compare and numeric:
        blocks.append(
            BarBlock(title="지원자별 총점", caption="고른 지원자의 총점이에요.", keys=numeric[:1], applicants=people)
        )
    total = bundle.total_key
    if total and sum(1 for fact in current if fact.key == total) >= 3:
        blocks.append(
            DistributionBlock(
                title="전체 지원자 분포",
                caption="전형 전체의 총점 분포예요." + (" 비교 대상의 위치를 표시했어요." if compare else ""),
                key=total,
                highlight=people if compare else [],
                split=None if compare else _pass_key(bundle),
                reference=[metric.id for metric in bundle.metrics if metric.key == total][:MAX_REFERENCE],
            )
        )
    return blocks


def _decisions(bundle: ReportBundle) -> list[str]:
    """전형마다 결정 key (document.decision, interview.decision …). 전형 순서다."""
    have = {fact.key for fact in bundle.facts}
    keys = [f"{stage_prefix(bundle.stages, stage)}.decision" for stage in bundle.stages]
    return [key for key in keys if key in have]


def _finalists(bundle: ReportBundle) -> list[str]:
    """최종 합격자. 마지막 전형 결정이 합격인 지원자다."""
    last = f"{stage_prefix(bundle.stages, bundle.stages[-1])}.decision"
    return [fact.applicant for fact in bundle.facts if fact.key == last and fact.value == "PASS"]


def evidence_block(bundle: ReportBundle, people: list[str]) -> EvidenceBlock | None:
    """대상마다 근거 한 항목. 정량 원문, 대상끼리 판정이 갈린 항목, 부분 · 미충족 항목 순으로 근거를 세 개까지
    고르고, 키워드는 그 근거가 받치는 항목 이름으로 쓴다. 근거가 없는 대상은 확인 필요로 둔다."""
    verdicts = {(fact.applicant, fact.key): fact.value for fact in bundle.facts}
    labels = {(fact.applicant, fact.key): fact.label for fact in bundle.facts}
    items = []
    for number in people:
        mine = [item for item in bundle.evidence if item.applicant == number]

        def rank(item: Evidence) -> tuple[int, int, int]:
            key = criterion_key(item.id.removeprefix(f"e-{item.applicant}-"))
            values = {verdicts.get((other, key)) for other in people}
            mixed = len(values - {None}) > 1
            quant = item.strength is Strength.QUANT
            weak = item.verdict not in POSITIVE
            return (0 if quant else 1, 0 if mixed else 1, 0 if weak else 1)

        chosen = sorted(mine, key=rank)[:MAX_EVIDENCE]
        if not chosen:
            continue

        def keyword(item: Evidence) -> str:
            # 근거가 받치는 항목 이름. 예전 묶음처럼 이름이 없으면 항목 값 이름, 그것도 없으면 판단 문장 앞부분
            key = criterion_key(item.id.removeprefix(f"e-{item.applicant}-"))
            return _short(item.label or labels.get((item.applicant, key)) or item.text)

        keywords = list(dict.fromkeys(keyword(item) for item in chosen))
        items.append(EvidenceItem(applicant=number, keywords=keywords[:4], evidence=[item.id for item in chosen]))
    if not items:
        return None
    return EvidenceBlock(title="지원자별 근거", items=items)


def score_rings(bundle: ReportBundle, people: list[str]) -> RingsBlock | None:
    """영역 점수 표. 점수가 빈(보류) 지원자는 화면이 '확인 필요'로 그리므로 모든 영역을 넣는다."""
    views = [
        RingView(label=area.label, keys=[area.score_key])
        for area in bundle.areas
        if area.score_key and score_view(bundle, [area.score_key])
    ]
    if len(views) < 2:
        return None
    return RingsBlock(title="영역 점수", caption="채운 칸이 많을수록 만점에 가까워요.", views=views, applicants=people)


def perspective_rings(bundle: ReportBundle, people: list[str]) -> RingsBlock | None:
    """관점별 항목 충족 표. 항목을 영역 안에서 2~3개씩 묶는다. 관점이 모자라면 None이다."""
    groups = _ring_groups(bundle, people)
    if len(groups) < MIN_PERSPECTIVES:
        return None
    labels = {fact.key: _short(fact.label) for fact in bundle.facts}
    return RingsBlock(
        title="관점별 충족 항목 수",
        caption="항목을 두세 개씩 묶어 충족한 항목 수를 칸으로 채웠어요.",
        views=[
            RingView(label=labels[keys[0]] + (f" 외 {len(keys) - 1}" if len(keys) > 1 else ""), keys=keys)
            for keys in groups
        ],
        applicants=people,
    )


def _ring_groups(bundle: ReportBundle, people: list[str]) -> list[list[str]]:
    """관점 표의 항목 묶음. 영역마다 항목을 둘씩 묶는다. 하나 남은 항목은 전체에서 한 번만 따로 두고,
    그다음부터는 앞 묶음에 붙여 셋으로 한다 (check의 한 항목짜리 관점 1개까지). 관점은 6개까지다."""
    items = _ring_items(bundle, people)
    by_area = [[key for key in area.keys if key in items] for area in bundle.areas]
    rest = [key for key in items if not any(key in keys for keys in by_area)]
    chunks: list[list[str]] = []
    single_used = False
    for keys in [*by_area, rest]:
        pairs = [keys[start : start + 2] for start in range(0, len(keys), 2)]
        if pairs and len(pairs[-1]) == 1 and len(pairs) > 1 and single_used:
            last = pairs.pop()
            pairs[-1] += last
        single_used = single_used or any(len(pair) == 1 for pair in pairs)
        chunks += pairs
    return chunks[:MAX_VIEWS]


def _short(label: str) -> str:
    """관점 이름에 쓰는 항목 이름. 앞의 코드를 떼고 낱말 단위로 짧게 줄인다
    ('Q-04 Git 기반 코드 리뷰와 협업 경험' → 'Git 기반 코드 리뷰와')."""
    head, _, rest = label.partition(" ")
    name = rest if _ITEM_CODE.fullmatch(head) and rest else label
    words: list[str] = []
    for word in name.split():
        if words and len(" ".join([*words, word])) > MAX_VIEW_NAME:
            break
        words.append(word)
    # 끝에 남은 연결 말은 뗀다 ('MySQL ·' → 'MySQL', 'Java 또는' → 'Java')
    while len(words) > 1 and words[-1] in _DANGLING:
        words.pop()
    return " ".join(words)


def _ring_items(bundle: ReportBundle, people: list[str]) -> list[str]:
    """관점 도넛 대신 쓰는 항목. 영역 항목과 있음 · 없음 key 중 비교 대상 모두에게 있는 것이다."""
    have = {key for keys in drawable(bundle).families.values() for key in keys}
    have |= {fact.key for fact in bundle.facts if fact.value in HAVE}
    candidates = [key for area in bundle.areas for key in area.keys] + sorted(have)
    common = set(_common_keys(bundle.facts, people, numeric=False))
    return [key for key in dict.fromkeys(candidates) if key in common][:MAX_RING_ITEMS]


def _pass_key(bundle: ReportBundle) -> str | None:
    """합격 · 불합격으로 나뉘는 두 갈래 판정 key."""
    return next((key for key, found in drawable(bundle).flags.items() if "PASS" in found), None)


def _drawable_blocks(bundle: ReportBundle) -> list[Block]:
    """영역 밖 자료(두 갈래 판정, 있음 · 없음 key, 조각 지표)를 모두 그린다."""
    data = drawable(bundle)
    blocks: list[Block] = []
    flags = list(data.flags)
    if len(flags) > 1:
        blocks.append(
            CrossBlock(
                title="두 판정을 함께 본 인원",
                caption="두 판정의 조합마다 인원을 셌어요.",
                row_key=flags[1],
                col_key=flags[0],
            )
        )
    if group_key := _pass_key(bundle):
        blocks += [
            ShareBlock(
                title="합격자와 전체의 비율",
                caption="있음으로 확인된 비율을 합격자와 전체로 견줘요.",
                keys=keys[:MAX_SHARE_KEYS],
                group_key=group_key,
                group_value="PASS",
            )
            for keys in data.families.values()
        ]
    # 조각 이름이 같은 group(예: '전체 신입' · '합격자 신입')끼리 구성 막대로 견준다
    labels = {metric.id: metric.label for metric in bundle.metrics}
    by_pieces: dict[tuple[str, ...], list[str]] = {}
    for group, ids in data.groups.items():
        by_pieces.setdefault(tuple(_piece(labels[i]) for i in ids), []).append(group)
    for groups in by_pieces.values():
        if 2 <= len(groups) <= 4:
            rows = [CompositionRow(label=_row_label(bundle, data.groups[g]), metrics=data.groups[g]) for g in groups]
            blocks.append(
                CompositionBlock(title="구간별 비율 비교", caption="같은 구간을 나란히 놓고 비율을 견줘요.", rows=rows)
            )
            continue
        blocks += [
            DonutBlock(title="부분별 비율", caption="전체에서 각 부분이 차지하는 비율이에요.", metrics=data.groups[g])
            for g in groups
            if 2 <= len(data.groups[g]) <= MAX_SLICES
        ]
    return blocks


def _piece(label: str) -> str:
    """조각 이름. 첫 낱말이 그룹 이름이면 뺀다 ('전체 신입' → 신입)."""
    return label.split(maxsplit=1)[-1]


def _row_label(bundle: ReportBundle, ids: list[str]) -> str:
    """구성 막대 이름. 조각 지표 이름의 첫 낱말(예: '전체 신입' → 전체)이다."""
    label = next(metric.label for metric in bundle.metrics if metric.id == ids[0])
    return label.split()[0]


def _area_blocks(
    bundle: ReportBundle, area: Area, people: list[str], numeric: list[str], verdicts: list[str], current: list[Fact]
) -> list[Block]:
    compare = bundle.kind is ReportKind.COMPARE
    items = [key for key in area.keys if key in verdicts][:MAX_MATRIX_KEYS]
    blocks: list[Block] = []
    if compare and area.score_key in numeric:
        reference = [metric.id for metric in bundle.metrics if metric.key == area.score_key][:MAX_REFERENCE]
        blocks.append(
            BarBlock(
                title=f"{area.label} 점수",
                caption=f"비교 대상의 {area.label} 점수예요.",
                keys=[area.score_key],
                applicants=people,
                reference=reference,
            )
        )
    elif not compare and area.score_key and sum(1 for fact in current if fact.key == area.score_key) >= 3:
        blocks.append(
            DistributionBlock(
                title=f"{area.label} 점수 분포", caption=f"전형 전체의 {area.label} 점수예요.", key=area.score_key
            )
        )
    if len(items) >= 2:
        if compare:
            blocks.append(
                MatrixBlock(
                    title="지원자별 항목 판정",
                    caption="지원자마다 항목을 충족했는지 보여 줘요.",
                    keys=items,
                    applicants=people,
                )
            )
        else:
            blocks.append(
                TallyBlock(title="항목별 판정 비율", caption="항목마다 판정 비율이에요.", keys=items, by="key")
            )
    return blocks


def _common_keys(facts: list[Fact], people: list[str], *, numeric: bool) -> list[str]:
    """people 모두에게 값이 있는 key. 묶음에 나온 순서다."""
    wanted = set(people)
    owners: dict[str, set[str]] = {}
    for fact in facts:
        if isinstance(fact.value, float | int) == numeric and fact.applicant in wanted:
            owners.setdefault(fact.key, set()).add(fact.applicant)
    order = Counter(fact.key for fact in facts)
    return [key for key in order if owners.get(key) == wanted]
