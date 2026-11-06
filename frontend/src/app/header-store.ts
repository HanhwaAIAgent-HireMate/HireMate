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

/**
 * 설정에 들어오기 전에 보던 화면. 설정의 [이전 화면]이 이곳으로 돌아간다.
 * 설정 메뉴끼리 옮겨 다녀도 바뀌지 않는다. 새 채용 만들기(/hr/recruitments/new)는 다시 열면 채용을 또 만들어 빼 둔다
 */
export const useReturnStore = create<{ path: string; remember: (path: string) => void }>((set) => ({
  path: '/hr',
  remember: (path) => set({ path }),
}))

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
