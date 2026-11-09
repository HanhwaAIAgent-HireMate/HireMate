import { UserRound } from 'lucide-react'

/**
 * 지원자 이름 앞에 두는 검정 테두리 원 아이콘. 전형 화면의 전체 지원자 · 선택 지원자와
 * 면접관 모드의 지원자 목록이 같은 모양을 쓴다. 화면 낭독기는 읽지 않는다 (이름이 바로 옆에 있다).
 */
export function ApplicantIcon() {
  return (
    <span
      aria-hidden
      className="flex size-[18px] shrink-0 items-center justify-center rounded-full border border-foreground text-foreground"
    >
      <UserRound className="size-3" />
    </span>
  )
}
