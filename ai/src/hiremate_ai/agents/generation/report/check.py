"""리포트 설계서 검사. 문제가 있으면 모델에게 고칠 이유로 보여 주고, 끝내 남으면 기본 구성(fallback.py)을 쓴다.

검사하는 것: 참조(지표 · 값 · 근거 · 지원자 · 영역)가 묶음에 있는가,
구성(요약, 섹션, 영역마다 섹션 하나, 시각화 셋 이상, 설명 한 줄), 부품이 그릴 만한 자료인가,
문장에 묶음에 없는 숫자 · 차별 조건 · 순위나 추천 표현이 없고 해요체인가.
"""

import re
from collections.abc import Iterable

from hiremate_ai.agents.generation.report.bundle import Area, Fact, ReportBundle, ReportKind
from hiremate_ai.agents.generation.report.derive import (
    cross_counts,
    drawable,
    ring_percent,
    scope_of,
    score_view,
    share_percents,
    split_keys,
    tally,
    top_percent,
    values_of,
)
from hiremate_ai.agents.generation.report.spec import (
    VISUAL_TYPES,
    BarBlock,
    Block,
    CompositionBlock,
    CrossBlock,
    DistributionBlock,
    DonutBlock,
    EvidenceBlock,
    KpiBlock,
    MatrixBlock,
    PositionBlock,
    RadarBlock,
    ReportSpec,
    RingsBlock,
    Section,
    ShareBlock,
    StackedBlock,
    TableBlock,
    TallyBlock,
    TextBlock,
)
from hiremate_ai.agents.guardrails import blocked_attribute

MIN_VISUALS = 3
MIN_KINDS = {ReportKind.STAGE: 4, ReportKind.FINAL: 4, ReportKind.COMPARE: 3}
"""리포트에 섞을 시각화 부품 종류 수. 같은 모양의 그래프만 되풀이하지 않게 한다."""
MAX_SECTIONS = 7
MAX_SECTION_BLOCKS = 3
MAX_COMPARED = 5
DATA_FIELDS = {
    "type",
    "keys",
    "key",
    "metrics",
    "applicants",
    "by",
    "views",
    "rows",
    "row_key",
    "col_key",
    "group_key",
}
"""부품이 그리는 자료. 같으면 같은 자료를 두 번 그린 것이다."""
MIN_PERSPECTIVES = 3
MAX_PERSPECTIVE_KEYS = 3
MAX_SINGLE_VIEWS = 1
"""항목 하나짜리 관점 수. 한 항목이면 도넛이 0% 아니면 100%라 견줄 것이 적다."""
"""관점 도넛의 관점 수. 요청 관점 하나만 보지 않고 여러 관점에서 견준다."""
MAX_BRIEF_SECTIONS = 2
MAX_BRIEF_BLOCKS = 3
MAX_BRIEF_SUMMARY = 200
MAX_CATEGORIES = 3
"""교차표 한 축의 판정 값 수."""

_APPLICANT = re.compile(r"(?<![A-Za-z0-9])[A-Z]-\d{3,}(?!\d)")
"""지원자번호. 한글 조사가 바로 붙어도(A-0007은) 찾는다."""
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_CODE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,3}-\d+(?!\d)")
"""항목 코드(Q-04, P-01)와 지원자번호. 문장 속 숫자 검사에서 뺀다."""
_RANKING = re.compile(
    r"\d+\s*위(?!치)|순위|가장\s*(?:우수|뛰어|낫|좋|적합|높|낮)|제일|"
    r"추천(?:해요|합니다|한다|드려요)|합격시키|채용하(?:세요|길)"
)
"""순위나 채용 추천 표현. 'AI 추천'(선발 인원 10배수)은 화면 용어라 막지 않는다."""
DESCRIBING = re.compile(r"보여\s*(?:줘요|드려요|줍니다)|정리했어요|비교해요|나타내요")
"""그림이 무엇인지 설명하는 말. takeaway는 설명이 아니라 그림에서 읽은 사실이다."""
_REFERENCE_WORD = re.compile(r"점선|기준선")
"""기준선을 말하는 caption. 그 부품에 reference가 있어야 한다."""
_UNCONFIRMED = re.compile(r"확인되지 않|드러나지 않|(?:서술|언급|근거|기록)이 없")
"""근거가 없다는 문장. 이런 evidence 항목만 근거 id 없이 쓸 수 있다."""
_VERDICT_CODE = re.compile(
    r"(?<![A-Za-z_])(?:NOT_MET|MET|PARTIAL|UNKNOWN|PASS|FAIL|NOT_RECOMMENDED|RECOMMENDED|NOT_CONFIRMED|CONFIRMED|UNCONFIRMED|CONFLICT)(?![A-Za-z_])"
)
"""판정 코드. 문장에는 충족 · 미충족 · 보류처럼 화면에 보이는 말로 쓴다."""
_FORMAL = re.compile(r"[가-힣]니다(?![가-힣])")
"""합니다체. 리포트 문장은 해요체로 쓴다."""
_PLAIN_END = re.compile(r"[가-힣](?<!니)다(?=[.!?](?:\s|$)|\s*$)")
"""평어(~다.)로 끝난 문장. 합니다체는 _FORMAL이 따로 잡는다."""
_COPULA = re.compile(r"(?:이하|이상|미만|초과|이내|정도|수준|이후|이전)여요|\d\s*(?:명|개|점|건|년|곳)여요")
"""'이하여요' · '11명여요'처럼 틀린 '~여요'. 받침이 없는 이름씨 뒤는 '예요', 받침이 있으면 '이에요'다.
'줄여요' · '보여요' 같은 움직씨는 맞는 말이라, 수량 · 범위 말 뒤만 잡는다."""


def _wrong_copula(text: str) -> str | None:
    match = _COPULA.search(text)
    return match.group() if match else None


_HANJA = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]+")
"""한자 · 일본 가나. 모델이 '項目', '조건を'처럼 낱말 하나를 섞어 쓰는 일이 있다. 리포트 문장은 한글로 쓴다."""
_VAGUE = re.compile(r"대부분|대다수")
"""세지 않은 양. 요약 · 읽을 점에서 쓰면 센 개수나 비율을 같이 쓴다."""
_KEY_NAME = re.compile(r"(?<![A-Za-z_])[a-z]+[0-9]*\.[a-z_*][a-z0-9_.*-]*")
"""값 key 이름(document.criterion.Q-05). 제목에는 담당자가 쓰는 말로 쓴다."""
_INNER_WORD = re.compile(r"선 위|선 아래|경계 그룹|판정 교차|값 정리|조각 지표")
"""개발하며 쓰던 말. 리포트만 보는 담당자는 뜻을 모른다."""
_VERDICT_WORD = re.compile(
    r"부분\s*충족|미충족|확인\s*필요|보류|(?<![부미])충족(?!\s*(?:하지|하진|못|여부|을|이\s*아))"
)
"""갈린 이유 문장 속 판정 말. '충족하지 못했어요'처럼 뒤에서 뒤집는 말은 판정으로 읽지 않는다."""
_VERDICT_WORDS = {"부분": "PARTIAL", "미충족": "NOT_MET", "확인": "UNKNOWN", "보류": "UNKNOWN", "충족": "MET"}
_VERDICT_LABELS = {"MET": "충족", "PARTIAL": "부분 충족", "NOT_MET": "미충족", "UNKNOWN": "확인 필요"}
_JOINED = re.compile(r"[\s()가-힣]{0,4}(?:와|과|,|·|및)\s*")
"""지원자번호 사이를 묶는 말. 'A-0004와 A-0006은 부분 충족'은 두 사람 모두의 판정이다."""
MAX_KEYWORDS = 4
MAX_KPI_METRICS = 5
MAX_KEYWORD_LENGTH = 20


def problems(spec: ReportSpec, bundle: ReportBundle) -> list[str]:
    """설계서의 문제. 빈 목록이면 그대로 쓸 수 있다."""
    found: list[str] = []
    if not spec.summary.strip():
        found.append("summary가 비어 있다")
    blocks = spec.all_blocks()
    visuals = [block for block in blocks if block.type in VISUAL_TYPES]
    found += _brief_problems(spec, visuals) if bundle.brief else _full_problems(spec, bundle, visuals)
    if bundle.kind is ReportKind.COMPARE:
        found += rings_problems([block for block in visuals if isinstance(block, RingsBlock)], bundle)
    areas = {area.id: area for area in bundle.areas}
    covered: list[str] = []
    seen: set[str] = set()
    for section_index, section in enumerate(spec.sections):
        where = f"sections[{section_index}]"
        if not section.takeaway.strip():
            found.append(f"{where}: 읽을 점(takeaway) 한 문장이 없다")
        elif describing := DESCRIBING.search(section.takeaway):
            found.append(
                f"{where}: takeaway가 그림 설명이다({describing.group()}). 그림에서 읽은 사실 · 차이를 한 문장으로 쓴다"
            )
        if not 1 <= len(section.blocks) <= MAX_SECTION_BLOCKS:
            found.append(f"{where}: 부품은 1~{MAX_SECTION_BLOCKS}개다")
        if section.area is not None:
            if (area := areas.get(section.area)) is None:
                found.append(f"{where}: 없는 영역 id: {section.area}")
            else:
                covered.append(area.id)
                found += [f"{where}: {problem}" for problem in _area_problems(section, area, bundle)]
        for index, block in enumerate(section.blocks):
            label = f"{where}.blocks[{index}]({block.type})"
            if block.type in VISUAL_TYPES:
                signature = block.model_dump_json(include=DATA_FIELDS)
                if signature in seen:
                    found.append(f"{label}가 앞 부품과 같은 자료를 다시 그린다")
                seen.add(signature)
            found += [f"{label}: {problem}" for problem in _block_problems(block, bundle)]
    if twice := sorted({area for area in covered if covered.count(area) > 1}):
        found.append(f"영역 섹션이 겹친다: {', '.join(twice)}. 영역마다 섹션 하나다")
    drawable_areas = [area for area in bundle.areas if _area_drawable(area, bundle)]
    if not bundle.brief and (missing := [area for area in drawable_areas if area.id not in covered]):
        found.append(f"영역 섹션이 빠졌다: {', '.join(f'{a.id}({a.label})' for a in missing)}")
    if bundle.kind is ReportKind.COMPARE:
        shown = {number for block in visuals for number in _applicants_of(block, bundle)}
        if missing_people := [number for number in bundle.targets if number not in shown]:
            found.append(f"비교 대상이 시각화 부품에 빠졌다: {', '.join(missing_people)}")
        evidence = [block for block in blocks if isinstance(block, EvidenceBlock)]
        if bundle.focus and not evidence:
            found.append(f"요청 관점({bundle.focus})의 근거 부품(evidence)이 없다")
        elif not bundle.brief and not evidence and bundle.evidence:
            found.append("근거 부품(evidence)이 없다. 근거 섹션을 두고 대상마다 한 항목(keywords와 근거 id)을 넣는다")
        cited = {item.applicant for block in evidence for item in block.items}
        have = {item.applicant for item in bundle.evidence}
        if evidence and (uncited := [n for n in bundle.targets if n in have and n not in cited]):
            found.append(f"근거 부품에 빠진 비교 대상이 있다: {', '.join(uncited)}")
        found += _split_problems(spec, bundle)
    found += _text_problems(spec, bundle)
    return found


def _brief_problems(spec: ReportSpec, visuals: list[Block]) -> list[str]:
    """간략히: 요약 두세 문장과 섹션 한두 개, 부품 셋까지."""
    found = []
    if len(spec.sections) > MAX_BRIEF_SECTIONS:
        found.append(f"간략히 요청이라 섹션은 {MAX_BRIEF_SECTIONS}개까지다")
    if len(spec.all_blocks()) > MAX_BRIEF_BLOCKS:
        found.append(f"간략히 요청이라 부품은 모두 합쳐 {MAX_BRIEF_BLOCKS}개까지다")
    if not visuals:
        found.append("시각화 부품이 하나 이상 있어야 한다")
    if len(spec.summary) > MAX_BRIEF_SUMMARY:
        found.append(f"간략히 요청이라 summary는 {MAX_BRIEF_SUMMARY}자까지다")
    return found


def _full_problems(spec: ReportSpec, bundle: ReportBundle, visuals: list[Block]) -> list[str]:
    found = []
    if not 2 <= len(spec.sections) <= MAX_SECTIONS:
        found.append(f"섹션은 2~{MAX_SECTIONS}개다")
    if len(visuals) < MIN_VISUALS:
        found.append(f"시각화 부품({' · '.join(sorted(VISUAL_TYPES))})이 모두 합쳐 {MIN_VISUALS}개 이상 있어야 한다")
    kinds = {block.type for block in visuals}
    if len(kinds) < MIN_KINDS[bundle.kind]:
        found.append(
            f"시각화 부품 종류가 {len(kinds)}가지뿐이다({', '.join(sorted(kinds))}). "
            f"{MIN_KINDS[bundle.kind]}가지 이상 섞는다. get_overview의 지표 · 값 key로 그릴 수 있는 부품을 고른다"
        )
    if bundle.kind is not ReportKind.COMPARE:
        found += _unused_data(visuals, bundle)
    return found


def rings_problems(rings: list[RingsBlock], bundle: ReportBundle) -> list[str]:
    """비교 리포트의 도넛 두 단. 영역 점수 도넛과, 항목을 관점으로 묶은 관점 도넛이다."""
    found = []
    scores = {area.score_key for area in bundle.areas if area.score_key}
    if scores and not any(
        all(len(view.keys) == 1 and view.keys[0] in scores for view in block.views)
        and scores <= {view.keys[0] for view in block.views}
        for block in rings
    ):
        found.append(
            "영역 점수 도넛(rings)이 없다. "
            f"views마다 영역 점수 key 하나({', '.join(sorted(scores))})를 넣은 rings를 둔다"
        )
    numeric = {fact.key for fact in bundle.facts if isinstance(fact.value, float | int)}
    perspectives = [
        block
        for block in rings
        if len(block.views) >= MIN_PERSPECTIVES and not any(key in numeric for view in block.views for key in view.keys)
    ]
    whole = [set(area.keys) for area in bundle.areas if len(area.keys) > MAX_PERSPECTIVE_KEYS]
    for block in perspectives:
        if sum(1 for view in block.views if len(view.keys) == 1) > MAX_SINGLE_VIEWS:
            found.append(
                f"항목 하나짜리 관점은 {MAX_SINGLE_VIEWS}개까지다. 관점마다 항목 2~{MAX_PERSPECTIVE_KEYS}개를 묶어야 "
                "도넛 비율이 0% · 100%로만 갈리지 않는다"
            )
        for view in block.views:
            if len(view.keys) > MAX_PERSPECTIVE_KEYS or set(view.keys) in whole:
                found.append(
                    f"관점 '{view.label}'이 항목을 너무 넓게 묶었다. 관점은 항목 이름으로 묶은 "
                    f"2~{MAX_PERSPECTIVE_KEYS}개 항목(하나짜리는 하나까지)이고 영역 전체나 '기타'로 두지 않는다"
                )
    if not perspectives:
        found.append(
            f"관점 도넛(rings)이 없다. 설계서의 perspectives 칸에 항목 판정 key를 관점 {MIN_PERSPECTIVES}~6개로 묶어 "
            "넣는다 (관점마다 항목 2~3개, 이름은 항목 내용을 보고 짧게: 협업, 연동 · API, 품질 · 테스트 등). "
            "요청 관점 말고도 여러 관점에서 비교 대상을 견준다"
        )
    return found


def _unused_data(visuals: list[Block], bundle: ReportBundle) -> list[str]:
    """전형 · 최종 리포트가 그리지 않은, 묶음에 있는 자료."""
    data = drawable(bundle)
    found = []
    crossed = {key for block in visuals if isinstance(block, CrossBlock) for key in (block.row_key, block.col_key)}
    if len(data.flags) > 1 and not crossed:
        found.append(f"두 갈래 판정 {', '.join(data.flags)}이 있는데 교차표(cross)가 없다")
    shared = {key for block in visuals if isinstance(block, ShareBlock) for key in block.keys}
    for prefix, keys in data.families.items():
        if not shared & set(keys):
            found.append(f"있음 · 없음 key {prefix}.*이 있는데 비율 막대(share)가 없다")
    pieces = {m for block in visuals if isinstance(block, DonutBlock) for m in block.metrics}
    pieces |= {m for block in visuals if isinstance(block, CompositionBlock) for row in block.rows for m in row.metrics}
    if unused := [group for group, ids in data.groups.items() if not pieces & set(ids)]:
        shown = "; ".join(f"{group}: {', '.join(data.groups[group])}" for group in unused)
        found.append(
            f"조각 지표를 그리지 않았다 ({shown}). donut은 metrics에 한 group의 지표 id를, "
            "composition은 rows마다 label과 한 group의 지표 id를 넣는다"
        )
    return found


def _area_problems(section: Section, area: Area, bundle: ReportBundle) -> list[str]:
    """영역 섹션은 그 영역 값을 그리는 시각화 부품이 있고, 다른 영역 값은 그리지 않는다.

    영역에 속하지 않은 값(결정, 역량 등)은 함께 그려도 된다.
    """
    own = _area_keys(area)
    others = {key for other in bundle.areas if other.id != area.id for key in _area_keys(other)}
    visuals = [block for block in section.blocks if block.type in VISUAL_TYPES]
    used = {key for block in visuals for key in _keys_of(block)}
    found = []
    if not used & own:
        found.append(f"{area.label} 영역 섹션에 그 영역 값({', '.join(sorted(own))})을 그린 시각화 부품이 없다")
    if outside := sorted(used & others):
        found.append(f"{area.label} 섹션에 다른 영역 key가 있다: {', '.join(outside)}. 그 영역 섹션에 그린다")
    return found


def _area_drawable(area: Area, bundle: ReportBundle) -> bool:
    """영역 섹션을 그릴 값이 있는가. 비교는 비교 대상 모두에게 있는 영역 값이 하나라도 있어야 한다.

    점수가 빈(보류) 지원자 때문에 그릴 값이 없는 영역까지 섹션을 요구하면 어떤 설계서도 통과하지 못한다.
    """
    own = _area_keys(area)
    people = set(scope_of(bundle))
    owners: dict[str, set[str]] = {}
    for fact in bundle.facts:
        if fact.key in own and fact.applicant in people:
            owners.setdefault(fact.key, set()).add(fact.applicant)
    if bundle.kind is ReportKind.COMPARE:
        return any(holders == people for holders in owners.values())
    return bool(owners)


def _area_keys(area: Area) -> set[str]:
    return set(area.keys) | ({area.score_key} if area.score_key else set())


def _block_problems(block: Block, bundle: ReportBundle) -> list[str]:
    found = []
    if block.type in VISUAL_TYPES and not getattr(block, "caption", "").strip():
        found.append("무엇을 보여 주는지 caption 한 줄이 없다")
    if _REFERENCE_WORD.search(getattr(block, "caption", "")) and not getattr(block, "reference", []):
        found.append("caption이 기준선을 말하는데 reference가 비었다. 기준선 지표를 넣거나 caption에서 뺀다")
    return found + block_data_problems(block, bundle)


def block_data_problems(block: Block, bundle: ReportBundle) -> list[str]:
    """부품이 그릴 자료의 문제(없는 key · 지표, 숫자가 아닌 값의 분포, 지원자 수 등). 문장 문제는 넣지 않는다.
    repair는 이 문제가 있는 시각화 부품을 그릴 수 없는 것으로 보고 뺀다."""
    found = []
    if unknown := [number for number in _listed_applicants(block) if number not in _scope(bundle)]:
        found.append(f"범위 밖 지원자번호: {', '.join(unknown)}")
    match block:
        case KpiBlock():
            found += _metric_problems(block.metrics, bundle)
            if not 2 <= len(block.metrics) <= MAX_KPI_METRICS:
                found.append(f"지표는 2~{MAX_KPI_METRICS}개다")
        case DonutBlock():
            found += _metric_problems(block.metrics, bundle)
            if not 2 <= len(block.metrics) <= 5:
                found.append("도넛 조각은 2~5개다")
            found += _group_problems(block.metrics, bundle)
        case CompositionBlock():
            if not 2 <= len(block.rows) <= 4:
                found.append("구성 막대는 2~4개다")
            for row in block.rows:
                found += _metric_problems(row.metrics, bundle) + _group_problems(row.metrics, bundle)
            if len({len(row.metrics) for row in block.rows}) > 1:
                found.append("구성 막대마다 같은 구간 수 · 순서로 지표를 넣는다")
        case CrossBlock():
            for key in (block.row_key, block.col_key):
                found += _verdict_key_problems(key, bundle, max_values=MAX_CATEGORIES)
            if block.row_key == block.col_key:
                found.append("행과 열 key가 같다")
        case ShareBlock():
            found += _grid_problems(block.keys, sorted(_scope(bundle)), bundle, numeric=False, full=False)
            found += _verdict_key_problems(block.group_key, bundle)
            if block.group_value not in set(values_of(bundle, block.group_key).values()):
                found.append(f"{block.group_key}에 없는 그룹 값: {block.group_value}")
            if not 2 <= len(block.keys) <= 8:
                found.append("비율을 견줄 key는 2~8개다")
        case RingsBlock():
            if not 2 <= len(block.views) <= 6:
                found.append("관점은 2~6개다")
            if not 2 <= len(block.applicants) <= MAX_COMPARED:
                found.append(f"지원자는 2~{MAX_COMPARED}명이다")
            for view in block.views:
                # 점수 칸은 점수가 빈(보류) 지원자를 '확인 필요'로 그리므로, 판정 칸만 모든 지원자에게 값이 있어야 한다
                if score_view(bundle, view.keys):
                    continue
                if any(ring_percent(bundle, view.keys, number) is None for number in block.applicants):
                    found.append(
                        f"관점 '{view.label}'을 그릴 수 없다. 영역 점수 key 하나, "
                        "또는 모든 지원자에게 있는 판정 key만 넣는다"
                    )
        case PositionBlock():
            found += _grid_problems(block.keys, block.applicants, bundle, numeric=True, full=True)
            if not 2 <= len(block.keys) <= 6:
                found.append("위치 칸의 key는 2~6개다")
            if len(block.applicants) > MAX_COMPARED:
                found.append(f"지원자는 {MAX_COMPARED}명까지다")
        case BarBlock() | StackedBlock() | RadarBlock():
            found += _grid_problems(block.keys, block.applicants, bundle, numeric=True, full=True)
            if isinstance(block, RadarBlock) and len(block.keys) < 3:
                found.append("레이더는 영역 key가 3개 이상이다")
            if isinstance(block, StackedBlock) and len(block.keys) < 2:
                found.append("쌓을 영역 key가 2개 이상이다. 하나면 bar로 그린다")
            if isinstance(block, BarBlock):
                found += _bar_problems(block, bundle)
            if len(block.applicants) > MAX_COMPARED:
                found.append(f"지원자는 {MAX_COMPARED}명까지다")
        case MatrixBlock():
            found += _grid_problems(block.keys, block.applicants, bundle, numeric=False, full=False)
            if len(block.keys) < 2:
                found.append("판정 항목이 하나뿐이다. matrix는 항목 2개 이상이고, 하나면 evidence로 쓴다")
        case TallyBlock():
            people = block.applicants or sorted(_scope(bundle))
            found += _grid_problems(block.keys, people, bundle, numeric=False, full=False)
            if len(block.keys) < 2:
                found.append("판정 key가 2개 이상이다")
        case TableBlock():
            found += _grid_problems(block.keys, block.applicants, bundle, numeric=None, full=False)
        case DistributionBlock():
            values = [fact for fact in bundle.facts if fact.key == block.key and _numeric(fact)]
            if len(values) < 3:
                found.append(f"{block.key}의 숫자 값이 3개보다 적어 분포를 그릴 수 없다")
            if block.highlight and bundle.kind is not ReportKind.COMPARE:
                found.append("전형 결과 리포트의 분포에는 지원자를 표시하지 않는다. highlight를 비운다")
            if len(block.highlight) > MAX_COMPARED:
                found.append(f"분포 위 표시는 {MAX_COMPARED}명까지다")
            found += _reference_problems(block.reference, [block.key], bundle)
            if block.split is not None:
                found += _verdict_key_problems(block.split, bundle, max_values=MAX_CATEGORIES)
        case EvidenceBlock():
            if not block.items:
                found.append("근거 항목이 없다")
            for index, item in enumerate(block.items):
                if not 1 <= len(item.keywords) <= MAX_KEYWORDS:
                    found.append(f"items[{index}]: 키워드 요약은 1~{MAX_KEYWORDS}개다")
                if long := [word for word in item.keywords if len(word) > MAX_KEYWORD_LENGTH]:
                    found.append(f"items[{index}]: 키워드는 {MAX_KEYWORD_LENGTH}자 안의 짧은 명사구다: {long[0]}")
                if not item.evidence:
                    if not _UNCONFIRMED.search(item.text):
                        found.append(f"items[{index}]: 근거 id가 없는 항목은 '확인되지 않았어요'처럼 확인 필요만 쓴다")
                    continue
                found += _evidence_problems(item.evidence, bundle, applicant=item.applicant)
        case TextBlock():
            found += _evidence_problems(block.evidence, bundle)
    return found


def _bar_problems(block: BarBlock, bundle: ReportBundle) -> list[str]:
    found = []
    if len(block.keys) * len(block.applicants) < 2 and not block.reference:
        found.append("값이 하나뿐이라 그릴 비교가 없다")
    maxes = {fact.max for fact in bundle.facts if fact.key in block.keys}
    if len(maxes) > 1:
        found.append("만점이 다른 key를 한 막대 묶음에 섞었다. 총점과 영역 점수는 stacked나 영역 섹션으로 나눈다")
    return found + _reference_problems(block.reference, block.keys, bundle)


def _metric_problems(ids: list[str], bundle: ReportBundle) -> list[str]:
    known = {metric.id for metric in bundle.metrics}
    if unknown := [metric for metric in ids if metric not in known]:
        return [f"없는 지표 id: {', '.join(unknown)}"]
    return []


def _group_problems(ids: list[str], bundle: ReportBundle) -> list[str]:
    """조각 지표는 모두 같은 group이어야 합이 전체가 된다."""
    groups = {metric.group for metric in bundle.metrics if metric.id in ids}
    if len(groups) != 1 or None in groups:
        return ["조각 지표는 같은 group의 지표다 (get_overview의 지표 group)"]
    return []


def _verdict_key_problems(key: str, bundle: ReportBundle, *, max_values: int | None = None) -> list[str]:
    values = set(values_of(bundle, key).values())
    if not values:
        return [f"없는 값 key: {key}"]
    if any(isinstance(value, float | int) for value in values):
        return [f"{key}는 판정이 아닌 숫자 값이다"]
    if max_values is not None and len(values) > max_values:
        return [f"{key}의 판정 값이 {max_values}가지를 넘어 나눠 그릴 수 없다"]
    return []


def _reference_problems(reference: list[str], keys: list[str], bundle: ReportBundle) -> list[str]:
    """기준선은 key가 하나인 부품에, 그 key를 집계한 지표만 쓴다."""
    metrics = {metric.id: metric for metric in bundle.metrics}
    found = []
    if unknown := [metric for metric in reference if metric not in metrics]:
        found.append(f"없는 기준선 지표 id: {', '.join(unknown)}")
    known = [metrics[metric] for metric in reference if metric in metrics]
    if known and (len(keys) != 1 or any(metric.key != keys[0] for metric in known)):
        found.append("기준선은 key가 하나인 부품에, 그 key를 집계한 지표만 쓴다")
    return found


def _grid_problems(
    keys: list[str], applicants: list[str], bundle: ReportBundle, *, numeric: bool | None, full: bool
) -> list[str]:
    """key × 지원자 칸. numeric이 True면 숫자, False면 판정 값만 받는다. full이면 모든 칸에 값이 있어야 한다."""
    found = []
    if not keys or not applicants:
        return ["keys와 applicants가 비어 있으면 안 된다"]
    by_cell = {(fact.applicant, fact.key): fact for fact in bundle.facts}
    known_keys = {fact.key for fact in bundle.facts}
    if unknown := [key for key in keys if key not in known_keys]:
        found.append(f"없는 값 key: {', '.join(unknown)}")
    cells = [by_cell.get((number, key)) for number in applicants for key in keys if key in known_keys]
    filled = [fact for fact in cells if fact is not None]
    if full and len(filled) < len(cells):
        found.append("값이 없는 칸이 있다. 모든 지원자에게 있는 key만 고른다")
    if not filled:
        found.append("그릴 값이 하나도 없다")
    if numeric is True and any(not _numeric(fact) for fact in filled):
        found.append("숫자가 아닌 값이 섞였다")
    if numeric is False and any(_numeric(fact) for fact in filled):
        found.append("판정이 아닌 숫자 값이 섞였다. 숫자는 bar · stacked · table로 그린다")
    return found


def _evidence_problems(ids: list[str], bundle: ReportBundle, applicant: str | None = None) -> list[str]:
    if not ids:
        return ["판단에는 근거 id가 1개 이상 있어야 한다"]
    evidence = {item.id: item for item in bundle.evidence}
    found = []
    if unknown := [evidence_id for evidence_id in ids if evidence_id not in evidence]:
        found.append(f"없는 근거 id: {', '.join(unknown)}. id는 짐작하지 말고 get_evidence로 받은 것만 쓴다")
        if applicant is not None:
            own = [item.id for item in bundle.evidence if item.applicant == applicant]
            found.append(f"{applicant}의 근거 id: {', '.join(own)}" if own else f"{applicant}는 근거 문장이 없다")
    if applicant is not None and any(evidence[i].applicant != applicant for i in ids if i in evidence):
        found.append(f"{applicant}의 근거가 아닌 id가 섞였다")
    return found


def _text_problems(spec: ReportSpec, bundle: ReportBundle) -> list[str]:
    allowed_numbers = numbers_in(bundle) | _drawn_numbers(spec, bundle) | _counted_numbers(bundle)
    known = {applicant.number for applicant in bundle.applicants}
    found = []
    for label, text in _texts(spec):
        found += sentence_problems(label, text, allowed_numbers, plain=".items[" not in label)
        vague = _VAGUE.search(text) if label.endswith(("summary", "takeaway")) else None
        if vague and not _NUMBER.search(_CODE.sub("", text)):
            found.append(f"{label}의 '{vague.group()}'는 count_values로 센 개수나 비율을 같이 쓴다")
        if unknown := sorted(set(_APPLICANT.findall(text)) - known):
            found.append(f"{label}에 범위 밖 지원자번호가 있다: {', '.join(unknown)}")
        if label.endswith(".title"):
            found += _title_problems(label, text)
    return found


def _title_problems(label: str, title: str) -> list[str]:
    """섹션 · 부품 제목. 그림이 무엇을 보여 주는지 담당자가 쓰는 말로 쓴다 (visual-guide의 '제목')."""
    found = []
    if key := _KEY_NAME.search(title):
        found.append(f"{label}에 값 key 이름이 있다: {key.group()}. 담당자가 쓰는 말로 쓴다")
    elif title.strip() and not _CODE.sub("", title).strip(" ·,/"):
        found.append(f"{label}가 항목 코드뿐이다: {title}. 항목 이름을 쓴다")
    if word := _INNER_WORD.search(title):
        found.append(f"{label}에 내부 용어가 있다: {word.group()}. 담당자가 쓰는 말로 풀어 쓴다")
    return found


def sentence_problems(label: str, text: str, allowed_numbers: set[str], *, plain: bool = True) -> list[str]:
    """리포트 문장 하나의 공통 검사. 차별 조건, 순위 · 추천 표현, 판정 코드, 합니다체 · 평어, 틀린 '~여요',
    자료에 없는 숫자를 찾는다. 설계서 문장과 분포 해설이 같이 쓴다.
    plain이 false면 평어를 보지 않는다. 근거 키워드처럼 분석 Agent의 판단 글(평어)을 옮긴 칸이다."""
    found = []
    if attribute := blocked_attribute(_CODE.sub("", text)):
        found.append(f"{label}에 채용 판단에 쓰면 안 되는 조건이 있다: {attribute}")
    if ranking := _RANKING.search(text):
        found.append(f"{label}에 순위나 추천 표현이 있다: {ranking.group()}")
    if code := _VERDICT_CODE.search(text):
        found.append(
            f"{label}에 판정 코드가 그대로 있다: {code.group()}. 충족 · 부분 · 미충족 · 보류처럼 화면 말로 쓴다"
        )
    if formal := _FORMAL.search(text):
        found.append(f"{label}는 해요체(~어요 · ~예요)로 쓴다: {formal.group()}")
    if plain and (ending := _PLAIN_END.search(text)):
        found.append(f"{label}는 해요체(~어요 · ~예요)로 쓴다: '{ending.group()}'로 끝난 평어가 있다")
    if copula := _wrong_copula(text):
        found.append(f"{label}의 '{copula}'는 틀린 말이다. '~예요'(받침 없음) · '~이에요'(받침 있음)로 쓴다")
    if hanja := _HANJA.search(text):
        found.append(f"{label}에 한자가 있다: {hanja.group()}. 한글로 쓴다")
    if unknown := sorted(set(_NUMBER.findall(_CODE.sub("", text))) - allowed_numbers):
        found.append(f"{label}에 묶음에 없는 숫자가 있다: {', '.join(unknown)}")
    return found


def _split_problems(spec: ReportSpec, bundle: ReportBundle) -> list[str]:
    """갈린 이유는 판정이 갈린 항목에만, 비교 대상의 근거 id로 쓴다. 문장 속 판정은 묶음의 판정과 같아야 한다."""
    keys = set(split_keys(bundle))
    owners = {item.id: item.applicant for item in bundle.evidence}
    found = []
    if keys and not spec.splits and not bundle.brief:
        found.append(
            f"판정이 갈린 항목({', '.join(sorted(keys))})이 있는데 splits가 비었다. "
            "갈린 항목마다 splits에 누가 무엇이 달랐는지 한 문장씩 쓴다"
        )
    verdicts = {(fact.applicant, fact.key): fact.value for fact in bundle.facts}
    for index, split in enumerate(spec.splits):
        if split.key not in keys:
            found.append(
                f"splits[{index}]: {split.key}는 판정이 갈린 항목이 아니다. 갈린 항목: {', '.join(sorted(keys))}"
            )
        if unknown := [id_ for id_ in split.evidence if owners.get(id_) not in bundle.targets]:
            found.append(f"splits[{index}]: 없는 근거 id: {', '.join(unknown)}")
        for number, said in verdict_claims(split.text):
            actual = verdicts.get((number, split.key))
            if actual in _VERDICT_LABELS and actual != said:
                found.append(
                    f"splits[{index}]: {number}의 판정은 {_VERDICT_LABELS[str(actual)]}인데 "
                    f"{_VERDICT_LABELS[said]}(으)로 썼다. 묶음의 판정대로 쓴다"
                )
    return found


def verdict_claims(text: str) -> list[tuple[str, str]]:
    """문장에서 '지원자번호 … 판정 말'을 짝지은 것. 다음 지원자번호가 나오기 전의 첫 판정 말을 그 지원자 것으로 본다."""
    claims: list[tuple[str, str]] = []
    waiting: list[str] = []
    position = 0
    tokens = sorted(
        [(m.start(), True, m.group()) for m in _APPLICANT.finditer(text)]
        + [(m.start(), False, m.group()) for m in _VERDICT_WORD.finditer(text)]
    )
    for start, is_applicant, value in tokens:
        if start < position:
            continue
        if is_applicant:
            if waiting and not _JOINED.fullmatch(text[position:start]):
                waiting = []
            waiting.append(value)
        elif waiting:
            word = value.replace(" ", "")
            code = next(code for prefix, code in _VERDICT_WORDS.items() if word.startswith(prefix))
            claims += [(number, code) for number in waiting]
            waiting = []
        position = start + len(value)
    return claims


def _texts(spec: ReportSpec) -> Iterable[tuple[str, str]]:
    yield "title", spec.title
    yield "summary", spec.summary
    for section_index, section in enumerate(spec.sections):
        where = f"sections[{section_index}]"
        yield f"{where}.title", section.title
        yield f"{where}.takeaway", section.takeaway
        for index, block in enumerate(section.blocks):
            yield f"{where}.blocks[{index}].title", block.title
            if caption := getattr(block, "caption", None):
                yield f"{where}.blocks[{index}].caption", caption
            if isinstance(block, TextBlock):
                yield f"{where}.blocks[{index}].text", block.text
            if isinstance(block, EvidenceBlock):
                for item_index, item in enumerate(block.items):
                    yield f"{where}.blocks[{index}].items[{item_index}]", " ".join([*item.keywords, item.text])
    for split_index, split in enumerate(spec.splits):
        yield f"splits[{split_index}]", split.text


def numbers_in(bundle: ReportBundle) -> set[str]:
    """문장에 써도 되는 숫자. 지표 · 값 · 만점, 인원, 영역 항목 수,
    근거 문장 · 항목 · 지표 · 전형 이름의 숫자(예: 3년, 5년 이상, 1차)다."""
    values: list[float] = [metric.value for metric in bundle.metrics]
    values += [fact.value for fact in bundle.facts if isinstance(fact.value, float | int)]
    values += [fact.max for fact in bundle.facts if fact.max is not None]
    values += [len(bundle.applicants), len(bundle.targets), len(bundle.stages)]
    values += [len(area.keys) for area in bundle.areas]
    numbers = {text for value in values for text in _spellings(value)}
    texts = [item.line() for item in bundle.evidence] + [stage.name for stage in bundle.stages] + [bundle.title]
    texts += [fact.label for fact in bundle.facts] + [metric.label for metric in bundle.metrics]
    texts += [area.label for area in bundle.areas]
    numbers |= {number for text in texts for number in _NUMBER.findall(text)}
    return numbers


def _drawn_numbers(spec: ReportSpec, bundle: ReportBundle) -> set[str]:
    """설계서 부품이 세어 그리는 숫자 (교차 인원, 그룹 비율 %, 상위 %). 그림에 나오므로 문장에 써도 된다."""
    values: list[float] = []
    for block in spec.all_blocks():
        match block:
            case CrossBlock():
                values += cross_counts(bundle, block.row_key, block.col_key).values()
            case ShareBlock():
                for group, everyone in share_percents(bundle, block.keys, block.group_key, block.group_value).values():
                    values += [group, everyone]
            case TallyBlock():
                people = block.applicants or scope_of(bundle)
                for key in block.keys:
                    counts, rate = tally(bundle, key, people)
                    values += [*counts.values(), rate]
            case RingsBlock():
                for view in block.views:
                    values += [r[0] for n in block.applicants if (r := ring_percent(bundle, view.keys, n)) is not None]
            case PositionBlock():
                for key in block.keys:
                    values += [p for n in block.applicants if (p := top_percent(bundle, key, n)) is not None]
    return {text for value in values for text in _spellings(value)}


def _counted_numbers(bundle: ReportBundle) -> set[str]:
    """count_values가 판정 key마다 세어 주는 인원과 충족 비율. 모델이 도구로 읽은 숫자라 문장에 써도 된다."""
    people = scope_of(bundle)
    values: list[float] = []
    for key in dict.fromkeys(fact.key for fact in bundle.facts if isinstance(fact.value, str)):
        counts, rate = tally(bundle, key, people)
        values += [*counts.values(), rate]
    return {text for value in values for text in _spellings(value)}


def _spellings(value: float) -> set[str]:
    return {f"{value:g}", f"{value:.1f}", str(round(value))}


def _numeric(fact: Fact) -> bool:
    return isinstance(fact.value, float | int)


def _scope(bundle: ReportBundle) -> set[str]:
    """부품에 쓸 수 있는 지원자. 비교면 비교 대상, 아니면 전형 전체다."""
    if bundle.kind is ReportKind.COMPARE:
        return set(bundle.targets)
    return {applicant.number for applicant in bundle.applicants}


def _keys_of(block: Block) -> list[str]:
    match block:
        case DistributionBlock():
            return [block.key]
        case CrossBlock():
            return [block.row_key, block.col_key]
        case RingsBlock():
            return [key for view in block.views for key in view.keys]
        case KpiBlock() | DonutBlock() | CompositionBlock() | EvidenceBlock() | TextBlock():
            return []
        case _:
            return block.keys


def _listed_applicants(block: Block) -> list[str]:
    match block:
        case (
            BarBlock()
            | StackedBlock()
            | RadarBlock()
            | PositionBlock()
            | RingsBlock()
            | MatrixBlock()
            | TallyBlock()
            | TableBlock()
        ):
            return block.applicants
        case DistributionBlock():
            return block.highlight
        case EvidenceBlock():
            return [item.applicant for item in block.items]
        case _:
            return []


def _applicants_of(block: Block, bundle: ReportBundle) -> list[str]:
    """부품이 그리는 지원자. 지원자를 비운 tally는 범위 전체다."""
    if isinstance(block, TallyBlock) and not block.applicants:
        return sorted(_scope(bundle))
    return _listed_applicants(block)
