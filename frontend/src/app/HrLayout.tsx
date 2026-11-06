import { ChevronRight, ExternalLink, Settings } from 'lucide-react'
import { useEffect } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation } from 'react-router'

import { useHeaderStore, useReturnStore } from '@/app/header-store'
import { LogoMark } from '@/app/LogoMark'
import { MemberMenu } from '@/app/MemberMenu'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useCompanyProfile } from '@/features/company/api'
import { InterviewNoticesBell } from '@/features/interview/InterviewNoticesBell'
import { rememberPostingStep } from '@/features/posting/posting-progress'
import { useMe, type Member } from '@/lib/auth'
import { cn } from '@/lib/utils'

// HR 콘솔. 로고를 누르면 채용 대시보드로, 오른쪽 위에서 설정을 연다 (기획 v7 §20)
export function HrLayout() {
  const me = useMe()
  const location = useLocation()
  useEffect(() => {
    if (me.data?.role === 'HR') rememberPostingStep(me.data, location.pathname)
  }, [me.data, location.pathname])
  const rememberReturn = useReturnStore((state) => state.remember)
  useEffect(() => {
    const path = location.pathname
    if (!path.startsWith('/hr/settings') && path !== '/hr/recruitments/new') {
      rememberReturn(path + location.search)
    }
  }, [location.pathname, location.search, rememberReturn])

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
  // 면접관 계정은 면접관 모드(내 면접)로 보낸다
  if (me.data.role !== 'HR') return <Navigate to="/interviewer" replace />

  return (
    <div className="flex h-screen flex-col bg-background">
      <HrHeader member={me.data} />
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

function HrHeader({ member }: { member: Member }) {
  const company = useCompanyProfile()
  const crumb = useHeaderStore((state) => state.crumb)
  return (
    // 알림 카드를 오른쪽으로 밀어 닫을 때 화면 밖으로 나간 부분이 가로 스크롤을 만들지 않게 가로만 자른다
    <header className="flex h-14 shrink-0 items-center gap-3 overflow-x-clip border-b px-5">
      <Link to="/hr" className="flex items-center gap-2.5 font-semibold">
        <LogoMark />
        <span>{company.data?.name ?? ''}</span>
      </Link>
      {crumb && (
        <nav className="flex min-w-0 items-center gap-1.5 text-sm" aria-label="현재 위치">
          <Link to="/hr" className="ml-2 text-muted-foreground hover:text-foreground">
            채용
          </Link>
          <ChevronRight className="size-3.5 text-muted-foreground" />
          <span className="truncate font-semibold">{crumb.title}</span>
          {crumb.status && (
            <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              {crumb.status}
            </span>
          )}
        </nav>
      )}
      <div className="ml-auto flex items-center gap-1">
        {crumb?.careersPath && (
          <Button variant="ghost" size="sm" asChild>
            <a href={crumb.careersPath} target="_blank" rel="noreferrer">
              <ExternalLink />
              채용 페이지
            </a>
          </Button>
        )}
        <NavLink
          to="/hr/settings"
          className={({ isActive }) =>
            cn(
              'inline-flex h-7 items-center gap-1 rounded-md px-2.5 text-[0.8rem] font-medium hover:bg-muted',
              isActive && 'bg-muted',
            )
          }
        >
          <Settings className="size-3.5" />
          설정
        </NavLink>
        <InterviewNoticesBell memberId={member.memberId} />
        <MemberMenu member={member} />
      </div>
    </header>
  )
}
