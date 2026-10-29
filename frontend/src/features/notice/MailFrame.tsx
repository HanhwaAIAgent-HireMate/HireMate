import { useState } from 'react'
import { Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import type { Schemas } from '@/lib/api/client'

export type MailPreview = Schemas['MailPreview']

/** 메일 색과 로고를 고르는 설정 (설정 › 안내 메일) */
const MAIL_SETTINGS_PATH = '/hr/settings/mail'

/** 줄여 보일 때 메일을 그리는 폭. 메일 본문 폭(600px)에 바깥 여백을 더한 크기다 */
const MAIL_WIDTH = 640

// 지원자가 받을 메일 모습. backend가 보낼 때와 같은 HTML을 만들어 주고, 화면은 스크립트를 막은 iframe에 넣는다.
// 스크립트 없이 같은 출처로만 열어, 다 그린 뒤 메일 길이에 맞게 높이를 늘린다.
// settingsLink가 있으면 그 글자로 설정 › 안내 메일로 가는 링크를 단다
// scale을 주면 메일을 실제 폭으로 그린 뒤 그 비율로 줄여 보인다. 좁은 칸에서도 PC 메일 모습 그대로 한눈에 본다
export function MailFrame({
  preview,
  title,
  settingsLink,
  scale,
}: {
  preview: MailPreview | undefined
  title: string
  /** 설정으로 가는 링크 글자. 예: 메일 색 · 로고 바꾸기 */
  settingsLink?: string
  /** 줄여 보일 비율 (0~1). 없으면 칸 폭 그대로 그린다 */
  scale?: number
}) {
  const [height, setHeight] = useState(480)
  if (!preview) return <Skeleton className="h-[480px] w-full rounded-lg" />
  const frame = (
    <iframe
      title={title}
      srcDoc={preview.html}
      sandbox="allow-same-origin"
      onLoad={(event) => {
        const page = event.currentTarget.contentDocument?.documentElement
        if (page) setHeight(page.scrollHeight)
      }}
      style={
        scale
          ? { height, width: MAIL_WIDTH, transform: `scale(${scale})`, transformOrigin: 'top left' }
          : { height }
      }
      className={scale ? 'rounded-lg border bg-white' : 'w-full rounded-lg border bg-white'}
    />
  )
  return (
    <div className="space-y-2">
      <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
        <span>
          제목 <span className="font-semibold text-foreground">{preview.subject}</span>
        </span>
        {settingsLink && (
          <Link to={MAIL_SETTINGS_PATH} className="ml-auto underline">
            {settingsLink}
          </Link>
        )}
      </p>
      {scale ? (
        <div
          className="overflow-hidden"
          style={{ width: MAIL_WIDTH * scale, height: height * scale }}
        >
          {frame}
        </div>
      ) : (
        frame
      )}
    </div>
  )
}
