import { useEffect } from "react"
import { MissionControlGlyph } from "./MissionControlIcons"

export default function Modal({ open, onClose, title, eyebrow, icon = "sparkle", size = "md", children, footer }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => {
      if (event.key === "Escape") onClose?.()
    }
    document.addEventListener("keydown", onKey)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  if (!open) return null

  const sizeClass = {
    sm: "max-w-md",
    md: "max-w-2xl",
    lg: "max-w-4xl",
    xl: "max-w-6xl",
  }[size] || "max-w-2xl"

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center p-4 sm:items-center">
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        className={`relative z-10 w-full ${sizeClass} max-h-[88vh] overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-[0_40px_80px_rgba(15,23,42,0.25)]`}
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
              <MissionControlGlyph name={icon} className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              {eyebrow ? (
                <div className="text-[10.5px] font-semibold uppercase tracking-[0.24em] text-indigo-600">
                  {eyebrow}
                </div>
              ) : null}
              <h2 className="truncate text-base font-semibold text-slate-900 sm:text-lg">{title}</h2>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:text-slate-700"
            aria-label="Close"
          >
            <MissionControlGlyph name="failed" className="h-4 w-4" />
          </button>
        </header>

        <div className="max-h-[64vh] overflow-y-auto px-6 py-5">{children}</div>

        {footer ? (
          <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 bg-slate-50/80 px-6 py-4">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  )
}
