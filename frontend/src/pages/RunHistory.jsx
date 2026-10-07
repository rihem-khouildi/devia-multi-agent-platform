import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import PageHeader from "../components/PageHeader"
import SectionCard from "../components/SectionCard"
import { formatDate, formatDuration, statusTone, toneClasses } from "../lib/format"
import { useRunsQuery } from "../lib/runQueries"

function StatusBadge({ status }) {
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium capitalize ${toneClasses(statusTone(status))}`}>
      {status}
    </span>
  )
}

export default function RunHistory() {
  const runsQuery = useRunsQuery()
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const runs = runsQuery.data?.runs || []

  const filteredRuns = useMemo(() => {
    const term = search.trim().toLowerCase()
    return runs.filter((run) => {
      const matchesStatus = statusFilter === "all" || run.status === statusFilter
      const haystack = `${run.story_id} ${run.story_title} ${run.run_id}`.toLowerCase()
      return matchesStatus && (!term || haystack.includes(term))
    })
  }, [runs, search, statusFilter])

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="History"
          title="Run History"
          description="Browse the full execution history with fast access to pipeline playback and quality results."
          meta={runsQuery.isFetching ? "Refreshing runs..." : `${filteredRuns.length} visible run(s)`}
          accentClass="text-[#00AEEF]"
        />

        <SectionCard>
          <div className="grid gap-4 border-b border-slate-200 px-6 py-5 md:grid-cols-[1fr_220px]">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">Search</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by story, title or run id"
                className="field-input"
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">Status</span>
              <select className="field-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">All statuses</option>
                <option value="running">Running</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
              </select>
            </label>
          </div>

          <div className="px-6 py-5">
            {runsQuery.isLoading ? <div className="text-sm text-slate-500">Loading run history...</div> : null}

            {runsQuery.error ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                {runsQuery.error.message || "Failed to load run history."}
              </div>
            ) : null}

            {!runsQuery.isLoading && !runsQuery.error && filteredRuns.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
                No runs match the current filters.
              </div>
            ) : null}

            {filteredRuns.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="min-w-full border-separate border-spacing-y-3">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-[0.18em] text-slate-500">
                      <th className="pb-1 pr-4 font-medium">Story</th>
                      <th className="pb-1 pr-4 font-medium">Status</th>
                      <th className="pb-1 pr-4 font-medium">Date</th>
                      <th className="pb-1 pr-4 font-medium">Duration</th>
                      <th className="pb-1 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRuns.map((run) => (
                      <tr key={run.run_id}>
                        <td className="rounded-l-3xl border-y border-l border-slate-200 bg-white px-4 py-4 align-top">
                          <div className="text-sm font-semibold text-slate-900">{run.story_title || run.story_id}</div>
                          <div className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">{run.story_id}</div>
                          <div className="mt-2 text-xs text-slate-500">Run ID: {run.run_id}</div>
                        </td>
                        <td className="border-y border-slate-200 bg-white px-4 py-4 align-top">
                          <StatusBadge status={run.status} />
                        </td>
                        <td className="border-y border-slate-200 bg-white px-4 py-4 align-top text-sm text-slate-600">
                          {formatDate(run.started_at)}
                        </td>
                        <td className="border-y border-slate-200 bg-white px-4 py-4 align-top text-sm text-slate-600">
                          {formatDuration(run.started_at, run.completed_at)}
                        </td>
                        <td className="rounded-r-3xl border-y border-r border-slate-200 bg-white px-4 py-4 align-top">
                          <div className="flex flex-wrap gap-2">
                            <Link to={`/pipeline/${run.run_id}`} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100">
                              View Pipeline
                            </Link>
                            <Link to={`/replay/${run.run_id}`} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">
                              Replay
                            </Link>
                            <Link to={`/quality/${run.run_id}`} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">
                              Quality
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>
    </div>
  )
}
