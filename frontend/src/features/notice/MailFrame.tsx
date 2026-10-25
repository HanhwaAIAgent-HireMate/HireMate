import { useState } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import type { Schemas } from '@/lib/api/client'

export type MailPreview = Schemas['MailPreview']

// 지원자가 받을 메일 모습. backend가 보낼 때와 같은 HTML을 만들어 주고, 화면은 스크립트를 막은 iframe에 넣는다.
// 스크립트 없이 같은 출처로만 열어, 다 그린 뒤 메일 길이에 맞게 높이를 늘린다
export function MailFrame({ preview, title }: { preview: MailPreview | undefined; title: string }) {
  const [height, setHeight] = useState(480)
  if (!preview) return <Skeleton className="h-[480px] w-full rounded-lg" />
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        제목 <span className="font-semibold text-foreground">{preview.subject}</span>
      </p>
      <iframe
        title={title}
        srcDoc={preview.html}
        sandbox="allow-same-origin"
        onLoad={(event) => {
          const page = event.currentTarget.contentDocument?.documentElement
          if (page) setHeight(page.scrollHeight)
        }}
        style={{ height }}
        className="w-full rounded-lg border bg-white"
      />
    </div>
  )
}
