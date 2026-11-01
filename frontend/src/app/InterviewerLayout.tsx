import { ChevronRight } from 'lucide-react'
import { Link, Navigate, Outlet, useLocation } from 'react-router'

import { useHeaderStore } from '@/app/header-store'
import { LogoMark } from '@/app/LogoMark'
import { MemberMenu } from '@/app/MemberMenu'
import { Skeleton } from '@/components/ui/skeleton'
import { useCompanyProfile } from '@/features/company/api'
import { useMe, type Member } from '@/lib/auth'

// 면접관 모드. 검은 위쪽 띠로 HR 콘솔과 구분한다. 지정된 면접 전형만 열고, 결정 · 선택 · 마감 기능은 없다.
// HR 계정도 면접관으로 지정되면 이 화면으로 면접을 본다
export function InterviewerLayout() {
  const me = useMe()
  const location = useLocation()

  if (me.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Skeleton className="h-6 w-40" />
      </div>
    )
  }
  if (!me.data) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <InterviewerHeader member={me.data} />
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

function InterviewerHeader({ member }: { member: Member }) {
  const company = useCompanyProfile()
  const crumb = useHeaderStore((state) => state.crumb)

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 bg-primary px-5 text-primary-foreground">
      <Link to="/interviewer" className="flex items-center gap-2.5 font-semibold">
        <LogoMark className="bg-primary-foreground text-primary" />
        <span>{company.data?.name ?? ''}</span>
      </Link>
      <nav className="flex min-w-0 items-center gap-1.5 text-sm" aria-label="현재 위치">
        <Link
          to="/interviewer"
          className="ml-2 text-primary-foreground/60 hover:text-primary-foreground"
        >
          내 면접
        </Link>
        {crumb && (
          <>
            <ChevronRight className="size-3.5 text-primary-foreground/60" />
            <span className="truncate font-semibold">{crumb.title}</span>
            {crumb.status && (
              <span className="rounded-md bg-primary-foreground/15 px-1.5 py-0.5 text-xs font-medium">
                {crumb.status}
              </span>
            )}
          </>
        )}
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-primary-foreground/30 px-2.5 py-0.5 text-xs font-semibold">
          <span className="size-1.5 rounded-full bg-emerald-400" />
          면접관 모드
        </span>
        {member.role === 'HR' && (
          <Link
            to="/hr"
            className="rounded-md px-2 py-1 text-xs text-primary-foreground/70 hover:text-primary-foreground"
          >
            HR 화면
          </Link>
        )}
        <MemberMenu member={member} className="hover:bg-primary-foreground/10" />
      </div>
    </header>
  )
}
