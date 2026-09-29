import { QueryClient } from "@tanstack/react-query"
import { Navigate, createBrowserRouter } from "react-router"

import { Layout } from "@/components/layout"
import { HomePage } from "@/pages/home"
import { LazySettingsPage, LazyVideoPage } from "@/pages/lazy"

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/v/:videoId", element: <LazyVideoPage /> },
      { path: "/settings", element: <Navigate to="/settings/health" replace /> },
      { path: "/settings/:tab", element: <LazySettingsPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
])
