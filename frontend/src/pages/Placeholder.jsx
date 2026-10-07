import SectionCard from "../components/SectionCard"

export default function Placeholder({
  title,
  description,
}) {
  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <div className="flex flex-col gap-2">
          <span className="inline-flex w-fit rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-sky-700">
            Coming soon
          </span>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">{title}</h1>
          <p className="max-w-2xl text-sm leading-6 text-slate-500">{description}</p>
        </div>

        <SectionCard className="overflow-hidden">
          <div className="border-b border-slate-200 px-6 py-5">
            <h2 className="text-lg font-medium text-slate-900">Frontend V1 Scope</h2>
            <p className="mt-1 text-sm text-slate-500">
              This workspace is intentionally stubbed for the demo. The navigation is active and ready for the next iteration.
            </p>
          </div>
          <div className="grid gap-4 px-6 py-6 md:grid-cols-3">
            <div className="surface-muted rounded-2xl p-4">
              <div className="text-sm font-medium text-slate-900">Planned</div>
              <div className="mt-2 text-sm text-slate-500">
                Detailed workflows, deeper data views, and operational controls can be added without changing the current shell.
              </div>
            </div>
            <div className="surface-muted rounded-2xl p-4">
              <div className="text-sm font-medium text-slate-900">Current state</div>
              <div className="mt-2 text-sm text-slate-500">
                Sidebar navigation is wired, theming matches the rest of the app, and this page keeps the demo polished instead of broken.
              </div>
            </div>
            <div className="surface-muted rounded-2xl p-4">
              <div className="text-sm font-medium text-slate-900">Suggested next step</div>
              <div className="mt-2 text-sm text-slate-500">
                Connect each module to its backend contract as it becomes available, reusing the same card and panel patterns.
              </div>
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  )
}
