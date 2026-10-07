import { useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import PageHeader from "../components/PageHeader"
import RunPicker from "../components/RunPicker"
import SectionCard from "../components/SectionCard"
import { api } from "../lib/api"
import { toneClasses } from "../lib/format"
import { useDefaultRunId, useRunsQuery } from "../lib/runQueries"

export default function RunQuality() {
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

  const qualityQuery = useQuery({
    queryKey: ["runs", selectedRunId, "quality"],
    queryFn: () => api.runs.quality(selectedRunId),
    enabled: Boolean(selectedRunId),
  })

  const quality = qualityQuery.data

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="Quality"
          title="Run quality metrics"
          description="Inspect gate results, quality metrics, and reported issues for a selected run."
          meta={qualityQuery.isFetching ? "Refreshing quality data..." : selectedRunId || "No run selected"}
          accentClass="text-[#5B5CFF]"
        />

        <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
          <RunPicker
            title="Inspect a run"
            description="Select a run to load `/runs/{run_id}/quality`."
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
              <h2 className="text-lg font-medium text-slate-900">Quality report</h2>
              <p className="mt-1 text-sm text-slate-500">Real gates and metrics returned by the backend quality endpoint.</p>
            </div>
            <div className="space-y-5 px-6 py-5">
              {qualityQuery.isLoading ? <div className="text-sm text-slate-500">Loading quality report...</div> : null}
              {qualityQuery.error ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  {qualityQuery.error.message || "Failed to load quality report"}
                </div>
              ) : null}

              {quality ? (
                <>
                  <div className={`rounded-3xl border p-4 ${toneClasses(quality.passed ? "success" : "danger")}`}>
                    <div className="text-sm text-slate-600">Overall result</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-900">{quality.passed ? "Passed" : "Failed"}</div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    {Object.entries(quality.gates || {}).map(([name, passed]) => (
                      <div key={name} className={`rounded-3xl border p-4 ${toneClasses(passed ? "success" : "danger")}`}>
                        <div className="text-sm text-slate-600">{name}</div>
                        <div className="mt-2 text-lg font-semibold text-slate-900">{String(passed)}</div>
                      </div>
                    ))}
                  </div>

                  <div className="surface-muted rounded-3xl p-4">
                    <div className="text-sm font-medium text-slate-900">Metrics</div>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      {Object.entries(quality.metrics || {}).map(([name, value]) => (
                        <div key={name} className="text-sm text-slate-600">
                          {name}: {String(value)}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="surface-muted rounded-3xl p-4">
                    <div className="text-sm font-medium text-slate-900">Issues</div>
                    <div className="mt-3 space-y-3">
                      {(quality.issues || []).length ? (
                        quality.issues.map((issue, index) => (
                          <div key={`${issue.message || "issue"}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-3 text-sm text-slate-600">
                            <div>{issue.message || JSON.stringify(issue)}</div>
                          </div>
                        ))
                      ) : (
                        <div className="text-sm text-slate-500">No issues reported.</div>
                      )}
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
