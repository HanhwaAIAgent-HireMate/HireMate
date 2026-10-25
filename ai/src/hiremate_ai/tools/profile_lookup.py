"""지원자 프로필 조회 도구 (PRD §10 get_candidate_evidence). Root Agent의 ReAct 도구 루프가 쓴다.

예: "@정유민 우리 회사랑 잘 맞는 것 같아?" → Root가 이 도구로 정유민의 프로필(항목 · 근거 · 출처)을 읽고 답한다.
원문 문서를 처음부터 다시 읽지 않고, 분석 Agent들이 미리 정리해 둔 내용을 바로 볼 수 있다.

이 파일에 있는 것
- read_profile: 조회 범위를 확인하고 프로필 한 명분을 DB에서 꺼낸다
- profile_text: 프로필을 모델이 읽을 글로 바꾼다
- profile_tool: Root 도구 루프에 넣을 @tool을 만든다

규칙
- 조회 범위(기업 · 채용 · 전형)는 모델이 정하지 못하게 도구 인자가 아니라 ToolRuntime의 context로 받는다 (규칙 4).
- 범위 밖 지원자는 프로필이 있어도 보여 주지 않는다.
- 읽기만 한다. 프로필을 바꾸는 도구는 만들지 않는다 (분석 Agent에 쓰기 도구를 주지 않음, 규칙 5).

Root에 연결하는 예 (지원자 번호 "C1"을 지원서 id로 바꾸는 함수는 Root가 넘긴다)
    def to_application_id(scope: ToolScope, ref: str) -> UUID | None:
        row = resolve_ref(scope.chat, ref)        # RootToolContext는 ToolScope를 물려받는다
        return row.application_id if row else None

    tool = profile_tool(session_factory(), resolve=to_application_id)
    toolkit = RootToolkit(..., answer_tools=(*ANSWER_TOOLS, tool))
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.profile import CandidateProfile, ItemCategory, ProfileItem, ProfileStatus, Verification
from hiremate_ai.tools.scope import ToolScope

type Sessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]
"""DB 세션을 여는 함수. 보통 db.session.session_factory()를 넘긴다."""

type ResolveRef = Callable[[ToolScope, str], UUID | None]
"""모델이 쓴 지원자 지칭("C1" 등)을 지원서 id로 바꾸는 함수. 찾지 못하면 None."""

OUT_OF_SCOPE = "조회 범위 밖의 지원자예요. 지원자 번호(C1 같은)로 다시 불러 주세요."
NO_PROFILE = "아직 이 지원자의 프로필이 없어요. 분석 전이거나 분석이 실패했어요. 제출 문서로 확인해 주세요."

# 글로 보여 줄 때의 분류 이름과 순서. 공고 조건 → 눈여겨볼 점 → 확인 필요 순으로 읽히게 한다
_CATEGORY_LABELS = {
    ItemCategory.QUALIFICATION: "자격 조건",
    ItemCategory.DOMAIN: "도메인",
    ItemCategory.EXPERIENCE: "직무 경험",
    ItemCategory.SKILL: "역량",
    ItemCategory.COMPANY_FIT: "기업 관련",
    ItemCategory.STRENGTH: "강점",
    ItemCategory.CHECK: "확인 필요",
}
_CATEGORY_ORDER = list(_CATEGORY_LABELS)
_STATUS_LABELS = {ProfileStatus.DONE: "분석 완료", ProfileStatus.CHECK: "확인 필요", ProfileStatus.FAILED: "분석 실패"}
# 항목의 확인 상태. 모델이 확인된 사실과 해석 · 미확인을 구분해 답하게 한다 (NFR-03)
_VERIFICATION_LABELS: dict[str, str] = {
    Verification.CONFIRMED: "확인됨",
    Verification.EVIDENCED: "근거 있음",
    Verification.UNCONFIRMED: "미확인",
    Verification.CONFLICT: "상충",
}


async def read_profile(session: AsyncSession, scope: ToolScope, application_id: UUID) -> CandidateProfile | None:
    """조회 범위 안의 지원자면 프로필을 돌려준다. 범위 밖이거나 프로필이 없으면 None."""
    # 1) 현재 전형의 지원자가 아니면 DB를 보지도 않는다
    if application_id not in scope.application_ids:
        return None
    # 2) 같은 지원서 id라도 기업 · 채용이 맞는 프로필만 꺼낸다 (다른 기업 데이터 차단)
    return await session.scalar(
        select(CandidateProfile).where(
            CandidateProfile.application_id == application_id,
            CandidateProfile.company_id == scope.company_id,
            CandidateProfile.recruitment_id == scope.recruitment_id,
        )
    )


def profile_text(profile: CandidateProfile) -> str:
    """프로필을 모델이 읽을 글로 바꾼다. 항목마다 근거 문장과 출처를 붙여 답에 근거를 달 수 있게 한다 (규칙 7).

    예)
    분석 상태: 분석 완료
    요약: 카드 결제 승인 · 정산 4년
    경력 4년 · 마지막 회사 한빛카드 · 서류 점수 88 · AI 기준 통과
    [도메인] 금융 (카드 결제 · 정산) — 근거: "한빛카드 결제플랫폼팀 2022.03 ~ 현재" (이력서)
    [확인 필요] 대용량 트래픽 수치 확인 필요 — 근거 문장 없음 (이력서)
    """
    # 1) 카드 앞면: 상태 · 요약 · 숫자. 값이 없으면 "알 수 없음"으로 적어 모델이 지어내지 않게 한다
    lines = [f"분석 상태: {_STATUS_LABELS.get(ProfileStatus(profile.status), profile.status)}"]
    if profile.summary:
        lines.append(f"요약: {profile.summary}")
    lines.append(" · ".join(_front_values(profile)))

    # 2) 카드 뒷면: 항목을 분류 순서대로, 같은 분류 안에서는 저장된 순서대로
    items = sorted(profile.items, key=lambda item: (_category_rank(item), item.created_at, item.id))
    lines += [_item_line(item) for item in items] or ["(정리된 항목이 없어요)"]
    return "\n".join(lines)


def profile_tool(sessions: Sessions, *, resolve: ResolveRef) -> BaseTool:
    """Root 도구 루프에 넣을 get_candidate_profile 도구를 만든다.

    sessions: DB 세션을 여는 함수 (예: session_factory())
    resolve: 모델이 쓴 지원자 번호를 지원서 id로 바꾸는 함수. Root가 자기 지원자 목록으로 만들어 넘긴다.
    """

    # @tool을 단 async 함수의 설명(docstring)이 모델에게 보이는 도구 설명이 된다.
    # runtime은 모델이 채우는 인자가 아니다. ToolAgent.run(context=...)으로 코드가 넣은 조회 범위가 들어온다.
    @tool
    async def get_candidate_profile(candidate: str, runtime: ToolRuntime[ToolScope]) -> str:
        """지원자 프로필을 읽는다. 분석 Agent들이 정리한 경력, 서류 점수, 경험 · 역량 항목과 근거 문장 · 출처가 있다.

        candidate는 지원자 번호(예: C1)다.
        """
        scope = runtime.context
        # 1) 지원자 번호 → 지원서 id. 모르는 번호면 범위 밖으로 답한다
        application_id = resolve(scope, candidate)
        if application_id is None or application_id not in scope.application_ids:
            return OUT_OF_SCOPE
        # 2) 부를 때마다 세션을 열고, 읽은 뒤 닫는다
        async with sessions() as session:
            profile = await read_profile(session, scope, application_id)
            # 3) 세션이 열려 있는 동안 글로 바꾼다 (닫힌 뒤에는 항목을 읽을 수 없다)
            return NO_PROFILE if profile is None else profile_text(profile)

    return get_candidate_profile


def uuid_ref(scope: ToolScope, ref: str) -> UUID | None:
    """기본 resolve: 지원서 id 문자열을 그대로 받는다. 테스트나 지원자 번호가 없는 곳에서 쓴다."""
    try:
        return UUID(ref.strip())
    except ValueError:
        return None


def _front_values(profile: CandidateProfile) -> list[str]:
    """카드 앞면의 숫자들. 없으면 '알 수 없음'."""
    career = (
        "경력 알 수 없음"
        if profile.career_years is None
        else "신입"
        if profile.career_years == 0
        else f"경력 {profile.career_years}년"
    )
    values = [career]
    if profile.last_company:
        values.append(f"마지막 회사 {profile.last_company}")
    values.append(f"서류 점수 {profile.document_score:g}" if profile.document_score is not None else "서류 점수 없음")
    passed = {True: "AI 기준 통과", False: "AI 기준 미달", None: "AI 기준 판단 없음"}[profile.passed]
    values.append(passed)
    return values


def _category_rank(item: ProfileItem) -> int:
    """분류 순서. 모르는 분류(나중에 더해진 것)는 맨 뒤."""
    try:
        return _CATEGORY_ORDER.index(ItemCategory(item.category))
    except ValueError:
        return len(_CATEGORY_ORDER)


def _item_line(item: ProfileItem) -> str:
    """항목 한 줄. 근거 문장이 있으면 따옴표로, 없으면 없다고 적고, 끝에 확인 상태를 붙인다."""
    try:
        label = _CATEGORY_LABELS[ItemCategory(item.category)]
    except ValueError:
        label = item.category
    evidence = f'근거: "{item.evidence}"' if item.evidence else "근거 문장 없음"
    # 모르는 값(나중에 더해진 상태)은 그대로 적는다
    state = _VERIFICATION_LABELS.get(item.verification, item.verification)
    return f"[{label}] {item.content} — {evidence} ({item.source}) · {state}"
