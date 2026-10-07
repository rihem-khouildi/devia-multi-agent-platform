import StatusBadge from "./StatusBadge"
import { MissionControlGlyph } from "./MissionControlIcons"

const iconShellClasses = {
  info: "bg-sky-50 text-sky-600 ring-1 ring-sky-100",
  success: "bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100",
  warning: "bg-amber-50 text-amber-600 ring-1 ring-amber-100",
  failed: "bg-rose-50 text-rose-600 ring-1 ring-rose-100",
  blocked: "bg-rose-100 text-rose-700 ring-1 ring-rose-100",
}

export default function SummaryCard({ title, value, badge, status = "info", icon = "file", onClick, hint }) {
  const iconTone = iconShellClasses[status] || iconShellClasses.info
  const interactive = typeof onClick === "function"

  const Wrapper = interactive ? "button" : "div"

  return (
    <Wrapper
      type={interactive ? "button" : undefined}
      onClick={interactive ? onClick : undefined}
      className={`surface-card group w-full rounded-[28px] p-5 text-left transition-transform duration-200 ${
        interactive ? "cursor-pointer hover:-translate-y-1 hover:shadow-[0_24px_60px_rgba(15,23,42,0.08)]" : "hover:-translate-y-1"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">{title}</p>
          <p className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
        </div>
        <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${iconTone}`}>
          <MissionControlGlyph name={icon} className="h-5 w-5" />
        </div>
      </div>
      <div className="mt-5 flex items-center justify-between gap-2">
        <StatusBadge status={status}>{badge}</StatusBadge>
        {interactive ? (
          <span className="inline-flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-400 transition group-hover:text-slate-600">
            {hint || "Open"}
            <MissionControlGlyph name="arrow" className="h-3 w-3" />
          </span>
        ) : null}
      </div>
    </Wrapper>
  )
}
