import { LogOut } from 'lucide-react'
import { useState } from 'react'

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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useLogout, type Member } from '@/lib/auth'
import { cn } from '@/lib/utils'

/** 헤더 오른쪽의 계정 메뉴: 이름 · 이메일과 로그아웃(확인 창). HR 콘솔과 면접관 모드가 같이 쓴다 */
export function MemberMenu({ member, className }: { member: Member; className?: string }) {
  const logout = useLogout()
  const [confirmLogout, setConfirmLogout] = useState(false)
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className={cn(
              'flex items-center gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-muted',
              className,
            )}
          >
            <span className="flex size-7 items-center justify-center rounded-full bg-muted text-xs font-semibold text-foreground">
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
    </>
  )
}
