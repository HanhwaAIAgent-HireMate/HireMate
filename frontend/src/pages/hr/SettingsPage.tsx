import { Check } from 'lucide-react'
import { NavLink, useParams } from 'react-router'

import { useCompanyProfile, usePostingSettings } from '@/features/company/api'
import { CompanyProfileForm } from '@/features/company/CompanyProfileForm'
import { NoticeTemplateForm } from '@/features/company/NoticeTemplateForm'
import { PostingSettingsForm } from '@/features/company/PostingSettingsForm'
import { cn } from '@/lib/utils'

const SECTIONS = [
  { key: 'company', label: '회사 소개', path: '/hr/settings' },
  { key: 'posting', label: '채용 공고', path: '/hr/settings/posting' },
  { key: 'mail', label: '안내 메일', path: '/hr/settings/mail' },
] as const

// 설정에는 회사 소개 · 채용 공고 · 안내 메일 세 가지만 있다 (기획 v7 §6)
export function SettingsPage() {
  const { section = 'company' } = useParams()
  const profile = useCompanyProfile()
  const posting = usePostingSettings()
  const done: Record<string, boolean> = {
    company: Boolean(profile.data?.intro.trim()),
    posting: Boolean(posting.data?.writingStyle.trim() || posting.data?.requiredNotices.length),
  }

  return (
    <div className="flex h-full">
      <aside className="w-[190px] shrink-0 border-r px-3 py-6">
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
              {item.key === 'mail' ? (
                <span className="text-xs text-muted-foreground">4종</span>
              ) : (
                done[item.key] && <Check className="size-3.5 text-muted-foreground" />
              )}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1 overflow-auto">
        {section === 'posting' ? (
          <PostingSettingsForm />
        ) : section === 'mail' ? (
          <NoticeTemplateForm />
        ) : (
          <CompanyProfileForm />
        )}
      </div>
    </div>
  )
}
