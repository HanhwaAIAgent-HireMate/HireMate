import { useEffect } from 'react'
import { create } from 'zustand'

/** HR 헤더의 채용 경로 표시. 예: 채용 › 백엔드 개발자 (Java/Spring) [전형 진행 중] */
export type HeaderCrumb = {
  title: string
  status?: string
  /** 게시한 공고가 있으면 오른쪽 위 [채용 페이지] 링크로 연다 */
  careersPath?: string
}

type HeaderState = {
  crumb: HeaderCrumb | null
  setCrumb: (crumb: HeaderCrumb | null) => void
}

export const useHeaderStore = create<HeaderState>((set) => ({
  crumb: null,
  setCrumb: (crumb) => set({ crumb }),
}))

/** 화면이 열려 있는 동안 헤더에 채용 경로를 표시한다. */
export function useHeaderCrumb(crumb: HeaderCrumb | null | undefined) {
  const setCrumb = useHeaderStore((state) => state.setCrumb)
  const title = crumb?.title
  const status = crumb?.status
  const careersPath = crumb?.careersPath
  useEffect(() => {
    setCrumb(title ? { title, status, careersPath } : null)
    return () => setCrumb(null)
  }, [setCrumb, title, status, careersPath])
}
