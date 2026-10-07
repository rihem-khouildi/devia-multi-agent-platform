import { NavLink } from "react-router-dom"
import { NAV } from "./Sidebar"
import { useTheme } from "../context/ThemeContext"

export default function MobileNav() {
  const { dark, toggle } = useTheme()

  return (
    <div className="border-b border-slate-200 bg-white/90 px-4 py-4 backdrop-blur xl:hidden dark:border-slate-700 dark:bg-slate-900/90">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,_#5B5CFF_0%,_#00AEEF_100%)] text-xs font-semibold text-white">
            DV
          </div>
          <div>
            <div className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100">Devia</div>
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">AI Software Factory</div>
          </div>
        </div>
        <button
          onClick={toggle}
          aria-label="Toggle theme"
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          {dark ? "☀️" : "🌙"}
        </button>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `whitespace-nowrap rounded-full border px-3 py-2 text-xs transition-colors ${
                isActive
                  ? "border-transparent bg-[linear-gradient(135deg,_#5B5CFF_0%,_#00AEEF_100%)] text-white"
                  : "border-slate-200 bg-white text-slate-600"
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </div>
    </div>
  )
}
