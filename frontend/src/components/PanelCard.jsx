export default function PanelCard({ title, subtitle, action, children, className = "" }) {
  return (
    <section className={`surface-card overflow-visible rounded-[30px] ${className}`}>
      {(title || subtitle || action) ? (
        <div className="flex flex-col gap-4 border-b border-slate-200/80 px-6 py-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            {title ? <h2 className="text-lg font-semibold tracking-tight text-slate-900">{title}</h2> : null}
            {subtitle ? <p className="mt-1 text-sm leading-6 text-slate-500">{subtitle}</p> : null}
          </div>
          {action ? <div className="min-w-0 max-w-full sm:shrink-0">{action}</div> : null}
        </div>
      ) : null}
      <div className="min-w-0 px-6 py-6">{children}</div>
    </section>
  )
}
