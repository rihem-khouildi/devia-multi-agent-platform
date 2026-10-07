export function formatDate(value) {
  if (!value) return "N/A"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export function formatDuration(startedAt, completedAt) {
  if (!startedAt) return "N/A"
  const start = new Date(startedAt).getTime()
  const end = completedAt ? new Date(completedAt).getTime() : Date.now()
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "N/A"

  const totalSeconds = Math.round((end - start) / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

export function statusTone(status) {
  const normalized = String(status || "").toLowerCase()
  if (["ok", "completed", "loaded", "available", "success"].includes(normalized)) return "success"
  if (["running", "pending"].includes(normalized)) return "warning"
  if (["failed", "unavailable", "error"].includes(normalized)) return "danger"
  return "default"
}

export function toneClasses(tone) {
  const tones = {
    default: "border-slate-200 bg-slate-50 text-slate-700",
    success: "border-emerald-200 bg-emerald-50 text-emerald-700",
    warning: "border-sky-200 bg-sky-50 text-sky-700",
    danger: "border-rose-200 bg-rose-50 text-rose-700",
  }
  return tones[tone] || tones.default
}
