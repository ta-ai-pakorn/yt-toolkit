import { QueryClient } from "@tanstack/react-query"
import { Navigate, createBrowserRouter } from "react-router"

import { Layout } from "@/components/layout"
import { RouteError } from "@/components/route-error"
import { HomePage } from "@/pages/home"
import { LazyBatchPage, LazyHistoryPage, LazySettingsPage, LazyVideoPage } from "@/pages/lazy"

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export const router = createBrowserRouter([
  {
    element: <Layout />,
    errorElement: <RouteError />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/v/:videoId", element: <LazyVideoPage /> },
      { path: "/batch", element: <LazyBatchPage /> },
      { path: "/history", element: <LazyHistoryPage /> },
      { path: "/settings", element: <Navigate to="/settings/general" replace /> },
      { path: "/settings/:tab", element: <LazySettingsPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
])
