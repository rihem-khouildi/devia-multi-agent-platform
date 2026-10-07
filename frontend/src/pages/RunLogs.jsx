import { useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import PageHeader from "../components/PageHeader"
import RunPicker from "../components/RunPicker"
import SectionCard from "../components/SectionCard"
import { api } from "../lib/api"
import { useDefaultRunId, useRunsQuery } from "../lib/runQueries"

export default function RunLogs() {
  const runsQuery = useRunsQuery()
  const runs = runsQuery.data?.runs || []
  const [selectedRunId, setSelectedRunId] = useDefaultRunId(runs)
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedRunId = searchParams.get("runId")

  useEffect(() => {
    if (requestedRunId && runs.some((run) => run.run_id === requestedRunId) && requestedRunId !== selectedRunId) {
      setSelectedRunId(requestedRunId)
    }
  }, [requestedRunId, runs, selectedRunId, setSelectedRunId])

  const logsQuery = useQuery({
    queryKey: ["runs", selectedRunId, "logs"],
    queryFn: () => api.runs.logs(selectedRunId),
    enabled: Boolean(selectedRunId),
    refetchInterval: 5000,
  })

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="Logs"
          title="Run logs"
          description="Review recent log lines filtered for the selected run when available."
          meta={logsQuery.isFetching ? "Refreshing logs..." : selectedRunId || "No run selected"}
          accentClass="text-[#00AEEF]"
        />

        <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
          <RunPicker
            title="Inspect a run"
            description="Select a run to load `/runs/{run_id}/logs`."
            runs={runs}
            selectedRunId={selectedRunId}
            onChange={(runId) => {
              setSelectedRunId(runId)
              setSearchParams(runId ? { runId } : {})
            }}
            loading={runsQuery.isFetching}
          />

          <SectionCard>
            <div className="border-b border-slate-200 px-6 py-5">
              <h2 className="text-lg font-medium text-slate-900">Tail logs</h2>
              <p className="mt-1 text-sm text-slate-500">Latest backend log lines relevant to the selected run.</p>
            </div>
            <div className="space-y-5 px-6 py-5">
              {logsQuery.isLoading ? <div className="text-sm text-slate-500">Loading logs...</div> : null}
              {logsQuery.error ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  {logsQuery.error.message || "Failed to load logs"}
                </div>
              ) : null}

              {logsQuery.data ? (
                <pre className="max-h-[36rem] overflow-auto rounded-3xl border border-slate-200 bg-slate-950 p-4 text-xs leading-6 text-slate-100">
                  {(logsQuery.data.logs || []).join("\n") || "No logs available."}
                </pre>
              ) : null}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
