import type { Member } from '@/lib/auth'

export type PostingStep = 'content' | 'poster' | 'publish'
type Owner = Pick<Member, 'companyId' | 'memberId'>

function key(owner: Owner, recruitmentId: string) {
  return `hiremate:posting-progress:${owner.companyId}:${owner.memberId}:${recruitmentId}`
}

/** 공고 내용이 아닌 마지막 편집 위치만 계정·기업·공고별로 이 브라우저에 보관한다. */
export function rememberPostingStep(owner: Owner, pathname: string): void {
  const match = /^\/hr\/recruitments\/([^/]+)\/posting(?:\/(poster|publish|status))?\/?$/.exec(
    pathname,
  )
  if (!match) return
  try {
    if (match[2] === 'status') localStorage.removeItem(key(owner, match[1]))
    else localStorage.setItem(key(owner, match[1]), match[2] ?? 'content')
  } catch {
    // 브라우저 저장소를 사용할 수 없어도 공고 작성과 기본 진입 경로는 유지한다.
  }
}

export function lastPostingStep(
  owner: Owner | null | undefined,
  recruitmentId: string,
): PostingStep | undefined {
  if (!owner) return undefined
  try {
    const step = localStorage.getItem(key(owner, recruitmentId))
    return step === 'content' || step === 'poster' || step === 'publish' ? step : undefined
  } catch {
    return undefined
  }
}
