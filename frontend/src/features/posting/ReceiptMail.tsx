import { Lock } from 'lucide-react'

import { VariableField } from '@/features/company/VariableField'
import { previewReceipt, RECEIPT_VARIABLES, type Receipt } from '@/features/posting/receipt'

// 접수 확인 메일 편집. 지원서를 내면 바로 가는 메일이라 HR이 게시 전에 확인하고, 게시하면 잠긴다
export function ReceiptMailEditor({
  value,
  requiredText,
  locked,
  onChange,
}: {
  value: Receipt
  requiredText: string
  locked: boolean
  onChange: (value: Receipt) => void
}) {
  return (
    <div className="space-y-2 rounded-lg border bg-background p-3 text-sm">
      {locked ? (
        <>
          <p className="font-semibold">{value.subject}</p>
          <p className="leading-6 whitespace-pre-line">{value.body}</p>
        </>
      ) : (
        <>
          <div className="flex items-center gap-2 border-b pb-2">
            <span className="shrink-0 text-xs text-muted-foreground">제목</span>
            <VariableField
              aria-label="접수 확인 메일 제목"
              value={value.subject}
              onChange={(subject) => onChange({ ...value, subject })}
              className="flex-1 font-semibold"
            />
          </div>
          <VariableField
            aria-label="접수 확인 메일 본문"
            value={value.body}
            onChange={(body) => onChange({ ...value, body })}
          />
          <p className="text-xs text-muted-foreground">
            {RECEIPT_VARIABLES.join(' ')}는 보낼 때 실제 값으로 바뀌어요.
          </p>
        </>
      )}
      <p className="flex items-center gap-1.5 border-t pt-2 text-xs text-muted-foreground">
        <Lock className="size-3.5" />
        {requiredText}
      </p>
    </div>
  )
}

// 게시 전 미리보기. 회사명 · 공고명은 이 공고 값, 지원자 값은 예시로 채운다
export function ReceiptMailPreview({
  receipt,
  requiredText,
  companyName,
  title,
}: {
  receipt: Receipt
  requiredText: string
  companyName: string
  title: string
}) {
  return (
    <div className="space-y-2 rounded-lg border p-3 text-xs">
      <p className="font-semibold">{previewReceipt(receipt.subject, companyName, title)}</p>
      <p className="leading-5 whitespace-pre-line">
        {previewReceipt(receipt.body, companyName, title)}
      </p>
      <p className="border-t pt-2 text-muted-foreground">{requiredText}</p>
    </div>
  )
}
