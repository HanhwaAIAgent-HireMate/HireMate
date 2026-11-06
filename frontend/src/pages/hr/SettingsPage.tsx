import { ArrowLeft, Check } from 'lucide-react'
import { Link, NavLink, useParams } from 'react-router'

import { useReturnStore } from '@/app/header-store'
import { Button } from '@/components/ui/button'
import { useCompanyProfile, usePostingSettings } from '@/features/company/api'
import { CompanyProfileForm } from '@/features/company/CompanyProfileForm'
import { CanvaConnection } from '@/features/company/CanvaConnection'
import { InterviewerAccounts } from '@/features/company/InterviewerAccounts'
import { MailStyleForm } from '@/features/company/MailStyleForm'
import { NoticeTemplateForm } from '@/features/company/NoticeTemplateForm'
import { PostingSettingsForm } from '@/features/company/PostingSettingsForm'
import { PosterBrandForm } from '@/features/company/PosterBrandForm'
import { cn } from '@/lib/utils'

const SECTIONS = [
  { key: 'company', label: '회사 소개', path: '/hr/settings' },
  { key: 'posting', label: '채용 공고', path: '/hr/settings/posting' },
  { key: 'mail', label: '안내 메일', path: '/hr/settings/mail' },
  { key: 'interviewers', label: '면접관', path: '/hr/settings/interviewers' },
] as const

// 설정: 회사 소개 · 채용 공고 · 안내 메일 (기획 v7 §6), 면접관 계정 (면접관 모드)
export function SettingsPage() {
  const { section = 'company' } = useParams()
  const profile = useCompanyProfile()
  const posting = usePostingSettings()
  // 설정에 들어오기 전에 보던 화면. 설정 메뉴끼리 옮겨 다녀도 그대로다
  const back = useReturnStore((state) => state.path)
  const done: Record<string, boolean> = {
    company: Boolean(profile.data?.intro.trim()),
    posting: Boolean(posting.data?.writingStyle.trim() || posting.data?.requiredNotices.length),
  }

  return (
    <div className="flex h-full">
      <aside className="w-[190px] shrink-0 border-r px-3 py-6">
        <Button asChild variant="ghost" size="sm" className="mb-3 text-muted-foreground">
          <Link to={back}>
            <ArrowLeft />
            이전 화면
          </Link>
        </Button>
        <h1 className="mb-4 px-2 text-lg font-bold">설정</h1>
        <nav className="space-y-1">
          {SECTIONS.map((item) => (
            <NavLink
              key={item.key}
              to={item.path}
              end
              className={cn(
                'flex items-center justify-between rounded-lg px-2.5 py-2 text-sm',
                section === item.key
                  ? 'bg-muted font-semibold'
                  : 'text-muted-foreground hover:bg-muted/60',
              )}
            >
              {item.label}
              {done[item.key] && <Check className="size-3.5 text-muted-foreground" />}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1 overflow-auto">
        {section === 'posting' ? (
          <>
            <PostingSettingsForm />
            <PosterBrandForm />
            <CanvaConnection />
          </>
        ) : section === 'mail' ? (
          <>
            <NoticeTemplateForm />
            <MailStyleForm />
          </>
        ) : section === 'interviewers' ? (
          <InterviewerAccounts />
        ) : (
          <CompanyProfileForm />
        )}
      </div>
    </div>
  )
}
