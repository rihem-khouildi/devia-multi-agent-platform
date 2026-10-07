import { Outlet } from "react-router-dom"
import MobileNav from "./MobileNav"
import Sidebar from "./Sidebar"

export default function AppLayout() {
  return (
    <div className="app-shell min-h-screen">
      <Sidebar />
      <main className="xl:ml-80 min-h-screen overflow-auto">
        <MobileNav />
        <Outlet />
      </main>
    </div>
  )
}
