import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'

import { HrLayout } from '@/app/HrLayout'
import { ApplyPage } from '@/pages/careers/ApplyPage'
import { PostingPage } from '@/pages/careers/PostingPage'
import { DashboardPage } from '@/pages/hr/DashboardPage'
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

export const routes: RouteObject[] = [
  { path: '/', element: <Navigate to="/hr" replace /> },
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
  // 지원자용 채용 페이지
  { path: '/careers/:postingId', element: <PostingPage /> },
  { path: '/careers/:postingId/apply', element: <ApplyPage /> },
]

export const router = createBrowserRouter(routes)
