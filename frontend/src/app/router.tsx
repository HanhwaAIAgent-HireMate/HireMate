import { createBrowserRouter, type RouteObject } from 'react-router'

import { HrLayout } from '@/app/HrLayout'
import { InterviewerLayout } from '@/app/InterviewerLayout'
import { ApplyPage } from '@/pages/careers/ApplyPage'
import { PostingPage } from '@/pages/careers/PostingPage'
import { DashboardPage } from '@/pages/hr/DashboardPage'
import { LandingPage } from '@/pages/hr/LandingPage'
import { LoginPage } from '@/pages/hr/LoginPage'
import { NoticeEditorPage } from '@/pages/hr/NoticeEditorPage'
import { PostingEditorPage } from '@/pages/hr/PostingEditorPage'
import { PostingPublishPage } from '@/pages/hr/PostingPublishPage'
import { PostingPosterPage } from '@/pages/hr/PostingPosterPage'
import { PostingStatusPage } from '@/pages/hr/PostingStatusPage'
import { ReportPage } from '@/pages/hr/ReportPage'
import { SettingsPage } from '@/pages/hr/SettingsPage'
import { SignupPage } from '@/pages/hr/SignupPage'
import { StageClosePage } from '@/pages/hr/StageClosePage'
import { StagePage } from '@/pages/hr/StagePage'
import { InterviewRoomPage } from '@/pages/interviewer/InterviewRoomPage'
import { MyInterviewsPage } from '@/pages/interviewer/MyInterviewsPage'

export const routes: RouteObject[] = [
  { path: '/', element: <LandingPage /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  {
    // HR 콘솔 (로그인 후)
    path: '/hr',
    element: <HrLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'settings/:section?', element: <SettingsPage /> },
      { path: 'recruitments/new', element: <PostingEditorPage /> },
      { path: 'recruitments/:recruitmentId/posting', element: <PostingEditorPage /> },
      { path: 'recruitments/:recruitmentId/posting/poster', element: <PostingPosterPage /> },
      { path: 'recruitments/:recruitmentId/posting/publish', element: <PostingPublishPage /> },
      { path: 'recruitments/:recruitmentId/posting/status', element: <PostingStatusPage /> },
      { path: 'recruitments/:recruitmentId/stages/:stageId', element: <StagePage /> },
      { path: 'recruitments/:recruitmentId/stages/:stageId/close', element: <StageClosePage /> },
      {
        path: 'recruitments/:recruitmentId/stages/:stageId/close/notices/:group',
        element: <NoticeEditorPage />,
      },
      { path: 'recruitments/:recruitmentId/report', element: <ReportPage /> },
    ],
  },
  {
    // 면접관 모드 (면접관 계정만. HR 계정은 /hr로 보낸다)
    path: '/interviewer',
    element: <InterviewerLayout />,
    children: [
      { index: true, element: <MyInterviewsPage /> },
      { path: 'stages/:stageId', element: <InterviewRoomPage /> },
    ],
  },
  // 개발용 리포트 미리보기. 개발 서버에서만 등록한다 (backend 연동 전 확인용)
  ...(import.meta.env.DEV
    ? [
        {
          path: '/dev/report',
          lazy: async () => ({
            Component: (await import('@/pages/hr/ReportPreviewPage')).ReportPreviewPage,
          }),
        },
      ]
    : []),
  // 지원자용 채용 페이지
  { path: '/careers/:postingId', element: <PostingPage /> },
  { path: '/careers/:postingId/apply', element: <ApplyPage /> },
]

export const router = createBrowserRouter(routes)
