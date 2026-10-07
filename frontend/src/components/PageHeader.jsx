export default function PageHeader({
  eyebrow,
  title,
  description,
  meta,
  accentClass = "text-[#5B5CFF]",
}) {
  return (
    <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
      <div>
        <p className={`text-xs font-semibold uppercase tracking-[0.28em] ${accentClass}`}>{eyebrow}</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">{description}</p>
      </div>
      <div className="rounded-full border border-slate-200 bg-white/70 px-4 py-2 text-sm text-slate-500 shadow-sm">{meta}</div>
    </div>
  )
}
