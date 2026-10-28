import type { ReactNode } from 'react'

/** 공고 내용, 포스터와 게시 단계의 제목/작업 버튼 위치를 같은 규격으로 유지한다. */
export function PostingStepHeader({
  title,
  caption,
  children,
}: {
  title: string
  caption?: string
  children: ReactNode
}) {
  return (
    <header
      className="flex min-h-16 shrink-0 flex-wrap items-center gap-3 border-b px-6 py-3 sm:h-16 sm:flex-nowrap sm:py-0"
      data-posting-step-header
    >
      <div className="flex min-w-0 items-center gap-3">
        <h1 className="shrink-0 text-xl font-bold">{title}</h1>
        {caption && <span className="truncate text-sm text-muted-foreground">{caption}</span>}
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2">{children}</div>
    </header>
  )
}
