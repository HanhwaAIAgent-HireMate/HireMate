import { Bell, ChevronRight, ExternalLink, LogOut, Settings } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation } from 'react-router'

import { useHeaderStore } from '@/app/header-store'
import { LogoMark } from '@/app/LogoMark'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { useCompanyProfile } from '@/features/company/api'
import { useLogout, useMe, type Member } from '@/lib/auth'
import { cn } from '@/lib/utils'

// HR 콘솔. 로고를 누르면 채용 대시보드로, 오른쪽 위에서 설정을 연다 (기획 v7 §20)
export function HrLayout() {
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
  if (me.data.role !== 'HR') return <InterviewerNotice member={me.data} />

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
  const logout = useLogout()
  const [confirmLogout, setConfirmLogout] = useState(false)

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b px-5">
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
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="알림">
              <Bell />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-64 text-sm text-muted-foreground">
            새 알림이 없어요.
          </PopoverContent>
        </Popover>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-muted">
              <span className="flex size-7 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                {member.name.slice(0, 1)}
              </span>
              {member.name}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal">
              <div className="font-medium">{member.name}</div>
              <div className="text-xs text-muted-foreground">{member.email}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setConfirmLogout(true)}>
              <LogOut />
              로그아웃
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <AlertDialog open={confirmLogout} onOpenChange={setConfirmLogout}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>로그아웃 하시겠습니까?</AlertDialogTitle>
              <AlertDialogDescription>{member.email} 계정에서 로그아웃해요.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>취소</AlertDialogCancel>
              <AlertDialogAction onClick={() => logout.mutate()}>로그아웃</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </header>
  )
}

// 면접관 화면은 아직 없다. 면접관 권한 범위(OI-08)가 정해지면 연다.
function InterviewerNotice({ member }: { member: Member }) {
  const logout = useLogout()
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-surface p-6 text-center">
      <LogoMark />
      <h1 className="text-lg font-semibold">{member.name}님, 면접관 화면은 준비 중이에요</h1>
      <p className="text-sm text-muted-foreground">
        면접 질문과 답변 기록은 지금은 채용 담당자 계정에서 입력해요.
      </p>
      <Button variant="outline" onClick={() => logout.mutate()}>
        로그아웃
      </Button>
    </div>
  )
}
