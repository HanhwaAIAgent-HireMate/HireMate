"""지원자 프로필 (FR-08, 13, 14).

분석 Agent(지원서 · 평가 · 면접)가 낸 결과를 지원자별로 쌓아 두고, Root Agent가 조건으로 지원자를 찾을 때 쓴다.
- CandidateProfile: 지원자 한 명당 한 줄. 경력 연수, 서류 점수처럼 조건 검색에 쓰는 값
- ProfileItem: 지원자 한 명당 여러 줄. 경험, 역량 같은 항목과 그 근거 문장, 출처

규칙
- 분석 Agent가 낸 값을 그대로 저장한다. 이 모듈은 점수를 다시 매기거나 문장을 고치지 않는다.
- 이름, 연락처는 backend에 있으므로 저장하지 않고 지원서 ID로만 연결한다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 저장하지 않는다 (아키텍처 규칙 6).
- 조회는 항상 기업 · 채용 범위로 거른다 (아키텍처 규칙 4).
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hiremate_ai.db.base import SCHEMA, Base


class ProfileStatus(StrEnum):
    """프로필 분석 상태."""

    DONE = "DONE"  # 분석을 마쳤다
    CHECK = "CHECK"  # 문서 본문이 비어 있는 등 근거가 부족해 담당자 확인이 필요하다
    FAILED = "FAILED"  # 분석이 실패했다. 마감 전에 다시 돌린다


class ItemCategory(StrEnum):
    """프로필 항목 분류. 새 분류가 필요하면 팀과 정한 뒤 여기에 더한다."""

    EXPERIENCE = "EXPERIENCE"  # 직무 경험 (예: 카드 결제 승인 시스템 개발 4년)
    DOMAIN = "DOMAIN"  # 업무 도메인 (예: 금융, 이커머스). "금융 경험자" 검색에 쓴다
    SKILL = "SKILL"  # 기술 · 역량 (예: Java, Spring, Kafka)
    QUALIFICATION = "QUALIFICATION"  # 공고 자격 조건 대조 결과 (예: 경력 3년 이상 충족)
    COMPANY_FIT = "COMPANY_FIT"  # 회사 인재상 · 문화와 관련된 경험
    STRENGTH = "STRENGTH"  # 평가 · 면접에서 드러난 강점
    CHECK = "CHECK"  # 근거가 부족해 확인이 필요한 점


class ItemAgent(StrEnum):
    """항목을 만든 분석 Agent. 같은 Agent가 다시 분석하면 그 Agent의 항목만 바꾼다."""

    APPLICATION = "application"  # 지원서 분석
    ASSESSMENT = "assessment"  # 평가 분석
    INTERVIEW = "interview"  # 면접 분석


class CandidateProfile(Base):
    """지원자 한 명의 프로필. 지원서(application_id)마다 하나다."""

    __tablename__ = "candidate_profiles"
    __table_args__ = (Index("ix_candidate_profiles_scope", "company_id", "recruitment_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # backend의 지원서 · 기업 · 채용 ID. 다른 스키마라 외래 키는 걸지 않는다
    application_id: Mapped[UUID] = mapped_column(unique=True)
    company_id: Mapped[UUID]
    recruitment_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(10))  # ProfileStatus 값
    # 조건 검색에 쓰는 값. 분석 전이거나 찾지 못하면 None
    career_years: Mapped[int | None]
    last_company: Mapped[str | None] = mapped_column(String(200))
    document_score: Mapped[int | None]
    passed: Mapped[bool | None]  # AI 기준 통과 여부. 미달자는 AI 탐색에서 뺀다 (FR-20)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["ProfileItem"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin", order_by="ProfileItem.created_at"
    )


class ProfileItem(Base):
    """프로필 항목 한 줄. 내용과 근거 문장, 출처를 함께 둔다 (아키텍처 규칙 7)."""

    __tablename__ = "profile_items"
    __table_args__ = (Index("ix_profile_items_profile_id", "profile_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.candidate_profiles.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(20))  # ItemCategory 값
    agent: Mapped[str] = mapped_column(String(20))  # ItemAgent 값
    content: Mapped[str] = mapped_column(Text)  # 정리한 내용 (예: "금융 (카드 결제 · 정산)")
    evidence: Mapped[str | None] = mapped_column(Text)  # 원문에서 찾은 근거 문장. 없으면 None
    source: Mapped[str] = mapped_column(String(50))  # 출처 (예: 이력서, 자기소개서, 평가 결과, 면접 답변)
    stage_id: Mapped[UUID | None]  # 평가 · 면접 항목이면 그 전형 ID. 지원서 항목은 None
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped[CandidateProfile] = relationship(back_populates="items")
