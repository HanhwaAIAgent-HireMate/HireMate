"""프로필 항목 확인 상태 (확인됨 · 근거 있음 · 미확인 · 상충)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) 빈 칸으로 먼저 더한다. 이미 저장된 항목이 있어서 바로 NOT NULL로 만들 수 없다
    op.add_column("profile_items", sa.Column("verification", sa.String(length=12), nullable=True), schema="ai")
    # 2) 이미 저장된 항목을 채운다
    #    - 근거 문장이 없으면 미확인
    #    - 면접 분석의 강점(STRENGTH)은 면접 답변으로 확인된 점이라 확인됨
    #    - 면접 분석의 나머지는 '아직 확인되지 않은 점'과 '어긋나는 점'이 섞여 있어 구분할 수 없으므로 미확인
    #    - 그 밖에 근거 문장이 있는 항목은 근거 있음
    op.execute(
        """
        UPDATE ai.profile_items
        SET verification = CASE
            WHEN evidence IS NULL THEN 'UNCONFIRMED'
            WHEN agent = 'interview' AND category = 'STRENGTH' THEN 'CONFIRMED'
            WHEN agent = 'interview' THEN 'UNCONFIRMED'
            ELSE 'EVIDENCED'
        END
        """
    )
    # 3) 모두 채웠으니 비울 수 없는 칸으로 바꾼다
    op.alter_column("profile_items", "verification", existing_type=sa.String(length=12), nullable=False, schema="ai")


def downgrade() -> None:
    op.drop_column("profile_items", "verification", schema="ai")
