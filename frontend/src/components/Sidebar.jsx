import { NavLink, useNavigate } from "react-router-dom"
import { useAuth } from "../context/AuthContext"
import { useTheme } from "../context/ThemeContext"

export const NAV = [
  { to: "/", label: "Dashboard", icon: "DB" },
  { to: "/stories", label: "User Stories", icon: "US" },
  { to: "/graphrag", label: "GraphRAG", icon: "KG" },
  { to: "/pipeline", label: "Pipeline", icon: "PL" },
  { to: "/projects", label: "Projects", icon: "PR" },
  { to: "/quality", label: "Quality Metrics", icon: "QA" },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const { dark, toggle } = useTheme()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate("/login", { replace: true })
  }

  return (
    <aside className="hidden fixed left-0 top-0 h-screen w-80 border-r border-slate-200/80 bg-white/85 backdrop-blur xl:flex xl:flex-col z-40 overflow-y-auto dark:border-slate-700/80 dark:bg-slate-900/85">
      <div className="border-b border-slate-200 px-6 py-6">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,_#5B5CFF_0%,_#00AEEF_100%)] text-sm font-semibold text-white shadow-[0_12px_30px_rgba(91,92,255,0.28)]">
            DV
          </div>
          <div>
            <div className="text-lg font-semibold tracking-tight text-slate-900">Devia</div>
            <div className="mt-0.5 text-xs font-medium uppercase tracking-[0.22em] text-slate-500">AI Software Factory</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {NAV.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm transition-all ${
                isActive
                  ? "bg-[linear-gradient(135deg,_rgba(91,92,255,0.12)_0%,_rgba(0,174,239,0.12)_100%)] text-slate-900 shadow-[0_12px_30px_rgba(15,23,42,0.06)]"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-600">
              {icon}
            </span>
            <span className="truncate">{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* User info + logout */}
      <div className="border-t border-slate-200 px-4 py-4">
        {user && (
          <div className="mb-3 flex items-center gap-3 rounded-2xl bg-slate-50 px-3 py-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[linear-gradient(135deg,_#5B5CFF_0%,_#00AEEF_100%)] text-xs font-bold text-white">
              {user.username.slice(0, 2).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-slate-900">{user.username}</div>
              <div className="truncate text-xs text-slate-500">{user.email}</div>
            </div>
          </div>
        )}
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2 rounded-2xl px-3 py-2 text-sm text-slate-500 transition-colors hover:bg-rose-50 hover:text-rose-600"
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-xl border border-slate-200 bg-white text-[11px] font-semibold">
            ↩
          </span>
          Sign out
        </button>
        <button
          onClick={toggle}
          aria-label="Toggle theme"
          className="mt-2 flex w-full items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          <span>{dark ? "☀️" : "🌙"}</span>
          <span>{dark ? "Mode clair" : "Mode sombre"}</span>
        </button>
        <div className="mt-3 px-1 text-xs font-medium text-slate-400">Devia UI v1.1.0</div>
      </div>
    </aside>
  )
}
