// 🎤 질문 담당(인사 · 실무) 태그. 누를 때마다 인사 ↔ 실무로 바뀐다 (10/30: 기본 선택 상자 대신)
//   면접관은 인사 · 실무 2명이라 선택지가 둘뿐이어서, 메뉴를 열지 않고 한 번 눌러 바꾸는 토글로 둔다
import { cn } from '@/lib/utils'

export type InterviewerRole = 'HR' | 'PRACTICAL'

// 담당별 이름과 색: 인사는 보라, 실무는 초록 (질문 유형 배지 색과 겹치지 않게)
const ROLE_STYLES: Record<InterviewerRole, { label: string; className: string }> = {
  HR: { label: '인사', className: 'border-indigo-200 bg-indigo-50 text-indigo-700' },
  PRACTICAL: { label: '실무', className: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
}

// 다음 담당: 인사 → 실무, 실무 → 인사. 담당이 비어 있던 옛 질문(null)은 인사부터 시작한다
function nextRole(role: InterviewerRole | null): InterviewerRole {
  return role === 'HR' ? 'PRACTICAL' : 'HR'
}

export function RoleTag({
  role,
  questionText,
  onChange,
  disabled = false,
}: {
  role: InterviewerRole | null
  /** 화면 읽기 프로그램이 어느 질문의 담당인지 읽을 수 있게 붙이는 질문 문장 */
  questionText: string
  /** 없으면 바꿀 수 없는 태그(지난 면접 기록 등)로 보여 준다 */
  onChange?: (role: InterviewerRole) => void
  disabled?: boolean
}) {
  const common = questionText === '1분 자기소개 부탁드립니다.'
  const style = role ? ROLE_STYLES[role] : null
  const label = style?.label ?? '담당 선택'
  const tagClass = cn(
    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs leading-5 font-semibold',
    style?.className ?? 'border-border bg-background text-muted-foreground',
  )
  const dot = <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />

  // 바꿀 수 없는 곳: 같은 모양의 글자 태그만 보여 준다 (커서 · 반응 없음)
  if (!onChange || common) {
    return (
      <span className={tagClass} aria-label={`${questionText} 담당: ${label}`}>
        {dot}
        {label}
      </span>
    )
  }

  const next = ROLE_STYLES[nextRole(role)].label
  const hint = `클릭하면 ${next}로 바꿔요`
  return (
    <button
      type="button"
      aria-label={`${questionText} 담당: ${label} (${hint})`}
      title={hint}
      disabled={disabled}
      onClick={() => onChange(nextRole(role))}
      className={cn(
        tagClass,
        // 누를 수 있다는 걸 알 수 있게: 손가락 커서 + 마우스를 올리면 테두리를 조금 진하게
        'cursor-pointer transition-colors hover:border-current focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
        'disabled:cursor-default disabled:opacity-60 disabled:hover:border-transparent',
      )}
    >
      {dot}
      {label}
    </button>
  )
}
