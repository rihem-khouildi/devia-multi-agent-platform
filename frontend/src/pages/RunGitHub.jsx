import { useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import PageHeader from "../components/PageHeader"
import RunPicker from "../components/RunPicker"
import SectionCard from "../components/SectionCard"
import { api } from "../lib/api"
import { useDefaultRunId, useRunsQuery } from "../lib/runQueries"

export default function RunGitHub() {
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

  const githubQuery = useQuery({
    queryKey: ["runs", selectedRunId, "github"],
    queryFn: () => api.runs.github(selectedRunId),
    enabled: Boolean(selectedRunId),
  })

  const github = githubQuery.data

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="GitHub"
          title="GitHub sync"
          description="Inspect commit and pull request information attached to a selected run."
          meta={githubQuery.isFetching ? "Refreshing GitHub metadata..." : selectedRunId || "No run selected"}
          accentClass="text-[#5B5CFF]"
        />

        <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
          <RunPicker
            title="Inspect a run"
            description="Select a run to load `/runs/{run_id}/github`."
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
              <h2 className="text-lg font-medium text-slate-900">GitHub metadata</h2>
              <p className="mt-1 text-sm text-slate-500">Commit, branch, and PR details if the run reached the sync step.</p>
            </div>
            <div className="space-y-5 px-6 py-5">
              {githubQuery.isLoading ? <div className="text-sm text-slate-500">Loading GitHub data...</div> : null}
              {githubQuery.error ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  {githubQuery.error.message || "Failed to load GitHub data"}
                </div>
              ) : null}

              {github ? (
                <div className="grid gap-4">
                  <div className="surface-muted rounded-3xl p-4">
                    <div className="text-sm text-slate-500">Available</div>
                    <div className="mt-2 text-lg font-semibold text-slate-900">{String(github.available)}</div>
                  </div>
                  <div className="surface-muted rounded-3xl p-4">
                    <div className="text-sm text-slate-500">Commit SHA</div>
                    <div className="mt-2 break-all text-sm text-slate-700">{github.commit_sha || "N/A"}</div>
                  </div>
                  <div className="surface-muted rounded-3xl p-4">
                    <div className="text-sm text-slate-500">Branch</div>
                    <div className="mt-2 text-sm text-slate-700">{github.branch || "N/A"}</div>
                  </div>
                  <div className="surface-muted rounded-3xl p-4">
                    <div className="text-sm text-slate-500">Pull request</div>
                    {github.pr_url ? (
                      <a href={github.pr_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-sm font-medium text-[#5B5CFF] hover:text-[#4547E5]">
                        {github.pr_url}
                      </a>
                    ) : (
                      <div className="mt-2 text-sm text-slate-700">N/A</div>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
