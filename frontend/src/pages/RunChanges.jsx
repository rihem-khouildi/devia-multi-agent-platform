import { useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import PageHeader from "../components/PageHeader"
import RunPicker from "../components/RunPicker"
import SectionCard from "../components/SectionCard"
import { api } from "../lib/api"
import { useDefaultRunId, useRunsQuery } from "../lib/runQueries"

export default function RunChanges() {
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

  const changesQuery = useQuery({
    queryKey: ["runs", selectedRunId, "changes"],
    queryFn: () => api.runs.changes(selectedRunId),
    enabled: Boolean(selectedRunId),
  })

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="Changes"
          title="Generated files"
          description="Browse the files produced for a selected run from `/runs/{run_id}/changes`."
          meta={changesQuery.isFetching ? "Refreshing file list..." : selectedRunId || "No run selected"}
          accentClass="text-[#00AEEF]"
        />

        <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
          <RunPicker
            title="Inspect a run"
            description="Select a run to load its generated file list."
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
              <h2 className="text-lg font-medium text-slate-900">File inventory</h2>
              <p className="mt-1 text-sm text-slate-500">Generated file paths returned by the backend.</p>
            </div>
            <div className="space-y-5 px-6 py-5">
              {changesQuery.isLoading ? <div className="text-sm text-slate-500">Loading file inventory...</div> : null}
              {changesQuery.error ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  {changesQuery.error.message || "Failed to load changes"}
                </div>
              ) : null}

              {changesQuery.data ? (
                <>
                  <div className="surface-muted rounded-3xl p-4">
                    <div className="text-sm text-slate-500">Output path</div>
                    <div className="mt-2 break-all text-sm text-slate-700">{changesQuery.data.output_path || "N/A"}</div>
                  </div>

                  <div className="surface-muted rounded-3xl p-4">
                    <div className="text-sm font-medium text-slate-900">Files</div>
                    <div className="mt-3 space-y-2">
                      {(changesQuery.data.files || []).length ? (
                        changesQuery.data.files.map((file) => (
                          <div key={file} className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
                            {file}
                          </div>
                        ))
                      ) : (
                        <div className="text-sm text-slate-500">No generated files recorded for this run.</div>
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
