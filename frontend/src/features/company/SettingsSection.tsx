import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** 설정 오른쪽 영역의 제목과 [저장] 버튼. */
export function SettingsSection({
  title,
  saving,
  onSave,
  wide,
  children,
}: {
  title: string
  saving?: boolean
  onSave?: () => void
  /** 넓은 화면에서 미리보기를 옆에 둘 만큼 넓힌다 */
  wide?: boolean
  children: ReactNode
}) {
  return (
    <section className={cn('mx-auto max-w-[760px] px-6 py-6', wide && 'xl:max-w-[1200px]')}>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-lg font-bold">{title}</h2>
        {onSave && (
          <Button onClick={onSave} disabled={saving}>
            저장
          </Button>
        )}
      </div>
      <div className="space-y-5">{children}</div>
    </section>
  )
}

/** 왼쪽 항목 이름과 오른쪽 입력을 한 줄로 둔다. */
export function SettingsRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[92px_1fr] items-start gap-4">
      <div className="pt-2 text-sm font-medium text-muted-foreground">{label}</div>
      <div className="min-w-0">{children}</div>
    </div>
  )
}
