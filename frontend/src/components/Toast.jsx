import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"
import { MissionControlGlyph } from "./MissionControlIcons"

const ToastContext = createContext({ push: () => {} })

const TONE = {
  info: { icon: "graph", chip: "border-sky-200 bg-sky-50 text-sky-700" },
  success: { icon: "success", chip: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  warning: { icon: "warning", chip: "border-amber-200 bg-amber-50 text-amber-700" },
  error: { icon: "failed", chip: "border-rose-200 bg-rose-50 text-rose-700" },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const counter = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback((toast) => {
    counter.current += 1
    const id = counter.current
    const next = {
      id,
      tone: "info",
      duration: 3500,
      ...toast,
    }
    setToasts((current) => [...current, next])
    if (next.duration > 0) {
      setTimeout(() => dismiss(id), next.duration)
    }
    return id
  }, [dismiss])

  const value = useMemo(() => ({ push, dismiss }), [push, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 top-4 z-[90] flex flex-col items-center gap-2 px-4 sm:right-4 sm:left-auto sm:items-end">
        {toasts.map((toast) => {
          const tone = TONE[toast.tone] || TONE.info
          return (
            <div
              key={toast.id}
              className={`pointer-events-auto flex max-w-sm items-start gap-3 rounded-2xl border bg-white px-4 py-3 shadow-[0_18px_45px_rgba(15,23,42,0.18)] ${tone.chip}`}
              role="status"
            >
              <MissionControlGlyph name={tone.icon} className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="min-w-0 flex-1">
                {toast.title ? (
                  <div className="text-sm font-semibold text-slate-900">{toast.title}</div>
                ) : null}
                {toast.description ? (
                  <div className="mt-0.5 text-xs leading-5 text-slate-600">{toast.description}</div>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                className="ml-2 rounded-full text-slate-400 transition hover:text-slate-600"
                aria-label="Dismiss"
              >
                <MissionControlGlyph name="failed" className="h-3.5 w-3.5" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  return context.push
}

export function useToastApi() {
  return useContext(ToastContext)
}

export default ToastProvider

// Convenience hook to ensure mounting always works.
export function useEnsureToastMounted() {
  useEffect(() => {}, [])
}
