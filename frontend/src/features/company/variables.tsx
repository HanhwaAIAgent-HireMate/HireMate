import type { ReactNode } from 'react'

import type { NoticeTemplateType } from '@/features/company/api'

export const NOTICE_VARIABLES = ['{지원자명}', '{회사명}', '{공고명}', '{전형명}'] as const

/** 접수 확인 메일에 쓸 수 있는 변수. 보낼 때 backend가 실제 값으로 바꾼다 */
export const RECEIPT_VARIABLES = ['{지원자명}', '{회사명}', '{공고명}', '{지원번호}'] as const

export const NOTICE_TYPE_LABELS: Record<NoticeTemplateType, string> = {
  NEXT_STAGE: '다음 전형 안내',
  REJECT: '불합격 안내',
  FINAL_PASS: '최종 합격 안내',
  FINAL_REJECT: '최종 불합격 안내',
}

/** {지원자명} 같은 변수를 보라색으로 표시한다. */
export function renderVariables(text: string): ReactNode[] {
  return text.split(/(\{[^{}\s]+\})/g).map((part, index) =>
    /^\{[^{}\s]+\}$/.test(part) ? (
      <span
        key={index}
        className="rounded-sm bg-ai-soft font-medium text-ai shadow-[0_0_0_2px_var(--ai-soft)]"
      >
        {part}
      </span>
    ) : (
      part
    ),
  )
}
