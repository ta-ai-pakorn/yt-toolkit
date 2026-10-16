import { QueryClient } from "@tanstack/react-query"
import { Navigate, createBrowserRouter } from "react-router"

import { Layout } from "@/components/layout"
import { RouteError } from "@/components/route-error"
import { HomePage } from "@/pages/home"
import { LazyBatchPage, LazyHistoryPage, LazySettingsPage, LazyVideoPage } from "@/pages/lazy"

// networkMode "always": backend อยู่ในเครื่องนี้ (127.0.0.1) ค่าเริ่มต้น "online" ของ react-query พักทุกคำขอเมื่อเบราว์เซอร์บอก offline
// (ถอดสาย ปิด Wi-Fi หรือ Windows เพิ่งเปลี่ยนเครือข่าย) ปุ่มจึงหมุนค้างโดยไม่มีคำขอออกไปเลย ทั้งที่แอพยังต่อได้
// ส่งไปเลยเสมอ: เน็ตหลุดจริงก็ได้ error ปกติแทนการค้างเงียบ คือ E_NETWORK จาก backend ("เน็ตหลุด ลองใหม่อีกครั้ง")
// หรือ E_OFFLINE ถ้าต่อ backend ไม่ได้
// refetchOnReconnect: networkMode "always" ทำให้ค่าเริ่มต้นของ react-query กลายเป็น false ตั้งกลับเป็น true
// เน็ตกลับมา (เหตุการณ์ online) = คำขอที่พลาดไปโหลดใหม่เองเหมือนเดิม · query ที่ตั้งค่านี้เองยังใช้ค่าของตัวเอง
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, refetchOnReconnect: true, networkMode: "always" },
    mutations: { networkMode: "always" },
  },
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
