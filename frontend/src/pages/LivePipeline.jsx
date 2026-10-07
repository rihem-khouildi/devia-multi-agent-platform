import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import PageHeader from "../components/PageHeader"
import SectionCard from "../components/SectionCard"
import RunTimeline from "../components/RunTimeline"
import ErrorCard from "../components/ErrorCard"
import FilesReviewTab from "../components/FilesReviewTab"
import { api } from "../lib/api"
import { formatDate, statusTone, toneClasses } from "../lib/format"
import { buildPipelineStepStates, calculatePipelineProgress, findActiveStep } from "../lib/pipelineSteps"

const TABS = [
  { key: "timeline", label: "Timeline" },
  { key: "errors", label: "Errors" },
  { key: "files", label: "Files Review" },
]

function StatusBadge({ status }) {
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium capitalize ${toneClasses(statusTone(status))}`}>
      {status || "unknown"}
    </span>
  )
}

function TabBar({ activeTab, onChange, errorsCount, pendingFiles }) {
  return (
    <div className="flex flex-wrap gap-2 border-b border-slate-200 px-6 py-4">
      {TABS.map((tab) => {
        const isActive = tab.key === activeTab
        const badge = tab.key === "errors" ? errorsCount : tab.key === "files" ? pendingFiles : 0

        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => onChange(tab.key)}
            className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition ${
              isActive
                ? "border-transparent bg-[linear-gradient(135deg,_#5B5CFF_0%,_#00AEEF_100%)] text-white shadow-[0_12px_30px_rgba(91,92,255,0.22)]"
                : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            {tab.label}
            {badge > 0 ? (
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${isActive ? "bg-white/20 text-white" : "bg-slate-100 text-slate-700"}`}>
                {badge}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

function ProgressPanel({ summary, files, progress, activeStep, isPolling }) {
  return (
    <SectionCard className="overflow-hidden">
      <div className="grid gap-6 px-6 py-6 lg:grid-cols-[1.25fr_0.75fr]">
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={summary?.status} />
            {isPolling ? (
              <span className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700">
                <span className="h-2 w-2 animate-pulse rounded-full bg-sky-500" />
                Polling every 2 seconds
              </span>
            ) : null}
          </div>

          <div>
            <div className="flex items-end justify-between gap-4">
              <div>
                <div className="text-sm font-medium text-slate-900">Pipeline progress</div>
                <div className="mt-1 text-sm text-slate-500">
                  {activeStep ? `Current focus: ${activeStep.label}` : "No active step detected yet."}
                </div>
              </div>
              <div className="text-3xl font-semibold tracking-tight text-slate-900">{progress}%</div>
            </div>
            <div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-[linear-gradient(135deg,_#5B5CFF_0%,_#00AEEF_100%)] transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          <div className="surface-muted rounded-3xl p-4">
            <div className="text-sm text-slate-500">Started</div>
            <div className="mt-2 text-sm font-medium text-slate-900">{formatDate(summary?.started_at)}</div>
          </div>
          <div className="surface-muted rounded-3xl p-4">
            <div className="text-sm text-slate-500">Generated files</div>
            <div className="mt-2 text-sm font-medium text-slate-900">{files?.total ?? summary?.files_generated ?? 0}</div>
          </div>
          <div className="surface-muted rounded-3xl p-4">
            <div className="text-sm text-slate-500">Human approval</div>
            <div className="mt-2 text-sm font-medium text-slate-900">
              {files?.all_approved ? "Approved" : `${files?.accepted ?? 0}/${files?.total ?? 0} accepted`}
            </div>
          </div>
          <div className="surface-muted rounded-3xl p-4">
            <div className="text-sm text-slate-500">GitHub push</div>
            <div className="mt-2 break-all text-sm font-medium text-slate-900">{summary?.commit_sha || "Waiting for approval"}</div>
          </div>
        </div>
      </div>
    </SectionCard>
  )
}

function SummaryStrip({ summary, files }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <div className="surface-muted rounded-3xl p-4">
        <div className="text-sm text-slate-500">Story</div>
        <div className="mt-2 text-sm font-medium text-slate-900">{summary?.story_title || summary?.story_id}</div>
        <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">{summary?.story_id}</div>
      </div>
      <div className="surface-muted rounded-3xl p-4">
        <div className="text-sm text-slate-500">Quality Gate</div>
        <div className="mt-2 text-sm font-medium text-slate-900">
          {summary?.all_gates_passed == null ? "Pending" : summary.all_gates_passed ? "Passed" : "Failed"}
        </div>
        <div className="mt-1 text-xs text-slate-500">Review score: {summary?.review_score ?? "N/A"}</div>
      </div>
      <div className="surface-muted rounded-3xl p-4">
        <div className="text-sm text-slate-500">Compile / Tests</div>
        <div className="mt-2 text-sm font-medium text-slate-900">
          {summary?.compile_success == null ? "Pending" : summary.compile_success ? "Compile OK" : "Compile failed"}
        </div>
        <div className="mt-1 text-xs text-slate-500">Coverage: {summary?.test_coverage ?? "N/A"}</div>
      </div>
      <div className="surface-muted rounded-3xl p-4">
        <div className="text-sm text-slate-500">Approval State</div>
        <div className="mt-2 text-sm font-medium text-slate-900">
          {files?.all_approved ? "Ready for push" : `${files?.pending ?? 0} pending / ${files?.rejected ?? 0} rejected`}
        </div>
        <div className="mt-1 text-xs text-slate-500">Run ID: {summary?.run_id}</div>
      </div>
    </div>
  )
}

export default function LivePipeline() {
  const { runId } = useParams()
  const [activeTab, setActiveTab] = useState("timeline")

  const summaryQuery = useQuery({
    queryKey: ["runs", runId, "live-summary"],
    queryFn: () => api.runs.get(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  })

  const runStatus = summaryQuery.data?.status
  const isPolling = runStatus === "running"

  const eventsQuery = useQuery({
    queryKey: ["runs", runId, "live-events"],
    queryFn: () => api.runs.events(runId),
    enabled: Boolean(runId),
    refetchInterval: isPolling ? 2000 : false,
  })

  const errorsQuery = useQuery({
    queryKey: ["runs", runId, "live-errors"],
    queryFn: () => api.runs.errors(runId),
    enabled: Boolean(runId),
    refetchInterval: isPolling ? 2000 : false,
  })

  const filesQuery = useQuery({
    queryKey: ["runs", runId, "live-files"],
    queryFn: () => api.runs.files(runId),
    enabled: Boolean(runId),
    // Keep polling until all files are approved, even after the run ends
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.all_approved) return false
      return 3000
    },
  })

  // Auto-switch to errors once when the run finishes with errors.
  // Using a ref so clicking back to "Timeline" never re-triggers the switch.
  const autoSwitchedRef = useRef(false)
  useEffect(() => {
    if (!isPolling && errorsQuery.data?.total > 0 && !autoSwitchedRef.current) {
      autoSwitchedRef.current = true
      setActiveTab("errors")
    }
  }, [isPolling, errorsQuery.data?.total])

  const summary = summaryQuery.data
  const events = eventsQuery.data?.events || []
  const errors = errorsQuery.data?.errors || []
  const files = filesQuery.data
  const stepStates = buildPipelineStepStates({ summary, events, files })
  const progress = calculatePipelineProgress(stepStates)
  const activeStep = findActiveStep(stepStates)

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="Live Demo"
          title="Live Pipeline"
          description="Premium jury view of the pipeline progression, review decisions, and release readiness for a single run."
          meta={runId ? `${runId}${runStatus ? ` · ${runStatus}` : ""}` : "No run selected"}
          accentClass="text-[#5B5CFF]"
        />

        <div className="flex flex-wrap gap-3">
          <Link to="/pipeline" className="btn-secondary">
            Back to runs
          </Link>
          {runId ? (
            <Link to={`/quality/${runId}`} className="btn-secondary">
              Open quality center
            </Link>
          ) : null}
          {runId ? (
            <Link to={`/monitor?runId=${runId}`} className="btn-secondary">
              Open advanced monitor
            </Link>
          ) : null}
        </div>

        {summaryQuery.error ? (
          <SectionCard className="border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
            {summaryQuery.error.message || "Failed to load this run."}
          </SectionCard>
        ) : null}

        {summary ? (
          <>
            <ProgressPanel summary={summary} files={files} progress={progress} activeStep={activeStep} isPolling={isPolling} />
            <SummaryStrip summary={summary} files={files} />

            <SectionCard className="overflow-hidden">
              <TabBar
                activeTab={activeTab}
                onChange={setActiveTab}
                errorsCount={errorsQuery.data?.total ?? 0}
                pendingFiles={files?.pending ?? 0}
              />

              <div className="min-h-[22rem]">
                {activeTab === "timeline" ? (
                  <div className="px-6 py-6">
                    <RunTimeline steps={stepStates} />
                  </div>
                ) : null}

                {activeTab === "errors" ? (
                  <div className="space-y-4 px-6 py-6">
                    {errorsQuery.isLoading ? <div className="text-sm text-slate-500">Loading errors...</div> : null}

                    {errorsQuery.error ? (
                      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                        {errorsQuery.error.message}
                      </div>
                    ) : null}

                    {!errorsQuery.isLoading && !errorsQuery.error && errors.length === 0 ? (
                      <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
                        No compile or test errors were recorded for this run.
                      </div>
                    ) : null}

                    {errors.map((error, index) => (
                      <ErrorCard key={`${error.step}-${index}`} error={error} />
                    ))}
                  </div>
                ) : null}

                {activeTab === "files" ? (
                  <FilesReviewTab runId={runId} runStatus={runStatus} pollMs={2000} />
                ) : null}
              </div>
            </SectionCard>
          </>
        ) : null}
      </div>
    </div>
  )
}
