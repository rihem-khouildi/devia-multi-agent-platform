/**
 * RunMonitor — unified live pipeline monitor + error viewer.
 *
 * Left panel  : run picker with live status badge
 * Right panel : two tabs
 *   "Timeline" — vertical step timeline from GET /runs/{id}/events (polls 2s)
 *   "Errors"   — structured errors from GET /runs/{id}/errors
 */
import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import PageHeader     from "../components/PageHeader"
import RunPicker      from "../components/RunPicker"
import SectionCard    from "../components/SectionCard"
import RunTimeline       from "../components/RunTimeline"
import ErrorCard         from "../components/ErrorCard"
import FilesReviewTab   from "../components/FilesReviewTab"
import LLMFixTab        from "../components/LLMFixTab"
import { api }        from "../lib/api"
import { toneClasses, statusTone, formatDate } from "../lib/format"
import { useDefaultRunId, useRunsQuery, useRunSummaryQuery, useRunEventsQuery, useRunErrorsQuery } from "../lib/runQueries"

// ── Tab bar ───────────────────────────────────────────────────────────────────

const TABS = [
  { key: "timeline", label: "Timeline" },
  { key: "errors",   label: "Errors" },
  { key: "files",    label: "Files Review" },
  { key: "llmfix",   label: "LLM Fix" },
]

function TabBar({ active, onChange, errorCount, pendingFiles, runStatus }) {
  const showFixBadge = errorCount > 0 && runStatus === "failed"
  return (
    <div className="flex border-b border-white/10 overflow-x-auto">
      {TABS.map((tab) => {
        const isActive = tab.key === active
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`relative flex shrink-0 items-center gap-2 px-5 py-3.5 text-sm font-medium transition-colors focus:outline-none ${
              isActive
                ? "border-b-2 border-sky-400 text-white"
                : "border-b-2 border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
            {tab.key === "errors" && errorCount > 0 && (
              <span className="rounded-full border border-rose-400/30 bg-rose-400/15 px-1.5 py-0.5 text-[10px] font-semibold text-rose-300">
                {errorCount}
              </span>
            )}
            {tab.key === "files" && pendingFiles > 0 && (
              <span className="rounded-full border border-amber-400/30 bg-amber-400/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
                {pendingFiles}
              </span>
            )}
            {tab.key === "llmfix" && showFixBadge && (
              <span className="rounded-full border border-violet-400/30 bg-violet-400/15 px-1.5 py-0.5 text-[10px] font-semibold text-violet-300">
                fix
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Status badge in run picker ────────────────────────────────────────────────

function LiveStatusBadge({ status }) {
  if (!status) return null
  const isRunning = status === "running"
  return (
    <span className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${toneClasses(statusTone(status))}`}>
      {isRunning && (
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400" />
      )}
      {status}
    </span>
  )
}

// ── Empty / Loading states ────────────────────────────────────────────────────

function Spinner({ label }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-white/80" />
      {label}
    </div>
  )
}

function EmptyState({ icon, title, subtitle }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-white/10 bg-white/3 py-10 text-center">
      {icon && <span className="text-3xl">{icon}</span>}
      <div className="text-sm font-medium text-slate-400">{title}</div>
      {subtitle && <div className="text-xs text-slate-600">{subtitle}</div>}
    </div>
  )
}

// ── Timeline tab ──────────────────────────────────────────────────────────────

function TimelineTab({ runId, runStatus, eventsQuery }) {
  const events = eventsQuery.data?.events ?? []
  const total  = eventsQuery.data?.total  ?? 0
  const isPolling = runStatus === "running"

  return (
    <div className="px-6 py-5">
      {/* Polling indicator */}
      {isPolling && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-sky-400/20 bg-sky-400/8 px-4 py-2.5">
          <span className="h-2 w-2 animate-pulse rounded-full bg-sky-400" />
          <span className="text-xs text-sky-300">Live — polling every 2 seconds</span>
        </div>
      )}

      {runStatus && !isPolling && (
        <div className={`mb-4 flex items-center gap-2 rounded-xl border px-4 py-2.5 ${
          runStatus === "completed"
            ? "border-emerald-400/20 bg-emerald-400/8"
            : "border-rose-400/20 bg-rose-400/8"
        }`}>
          <span className={`text-xs ${runStatus === "completed" ? "text-emerald-300" : "text-rose-300"}`}>
            {runStatus === "completed" ? "✓ Pipeline completed" : "✗ Pipeline failed"} · {total} event{total !== 1 ? "s" : ""} recorded
          </span>
        </div>
      )}

      {eventsQuery.isLoading && !events.length && <Spinner label="Loading timeline…" />}

      {eventsQuery.error && (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
          {eventsQuery.error.message}
        </div>
      )}

      {!eventsQuery.isLoading && !eventsQuery.error && events.length === 0 && (
        <EmptyState
          icon="⏳"
          title="No events yet"
          subtitle="Events will appear here as the pipeline progresses."
        />
      )}

      {events.length > 0 && (
        <RunTimeline events={events} runStatus={runStatus} />
      )}
    </div>
  )
}

// ── Errors tab ────────────────────────────────────────────────────────────────

function ErrorsTab({ runId, runStatus, errorsQuery }) {
  const errors = errorsQuery.data?.errors ?? []
  const total  = errorsQuery.data?.total  ?? 0

  return (
    <div className="space-y-4 px-6 py-5">
      {errorsQuery.isLoading && <Spinner label="Loading errors…" />}

      {errorsQuery.error && (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
          {errorsQuery.error.message}
        </div>
      )}

      {errorsQuery.data && total === 0 && (
        <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/8 p-5">
          <div className="flex items-center gap-2.5">
            <span className="text-xl text-emerald-400">✓</span>
            <div>
              <div className="text-sm font-semibold text-emerald-200">No errors recorded</div>
              <div className="mt-0.5 text-xs text-emerald-400/70">
                {runStatus === "running"
                  ? "The pipeline is still running — errors will appear here if any step fails."
                  : "The pipeline completed without compile or test failures."}
              </div>
            </div>
          </div>
        </div>
      )}

      {errors.map((error, i) => (
        <ErrorCard key={`${error.step}-${i}`} error={error} />
      ))}
    </div>
  )
}

// ── Run info strip ────────────────────────────────────────────────────────────

function RunInfoStrip({ summary }) {
  if (!summary) return null
  return (
    <div className="grid grid-cols-2 gap-2 border-b border-white/8 px-6 py-3 sm:grid-cols-4">
      {[
        { label: "Status",    value: summary.status,                      tone: statusTone(summary.status) },
        { label: "Started",   value: formatDate(summary.started_at),      tone: "default" },
        { label: "Compile",   value: summary.compile_success == null ? "—" : summary.compile_success ? "✓ OK" : "✗ Failed", tone: summary.compile_success ? "success" : summary.compile_success === false ? "danger" : "default" },
        { label: "Coverage",  value: summary.test_coverage != null ? `${summary.test_coverage}%` : "—", tone: "default" },
      ].map(({ label, value, tone }) => (
        <div key={label} className="flex flex-col gap-0.5">
          <span className="text-[10px] uppercase tracking-widest text-slate-600">{label}</span>
          <span className={`text-xs font-medium ${toneClasses(tone)} rounded-md border px-2 py-1 text-center`}>
            {value}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function RunMonitor() {
  const runsQuery   = useRunsQuery()
  const runs        = runsQuery.data?.runs ?? []
  const [selectedRunId, setSelectedRunId] = useDefaultRunId(runs)
  const [searchParams, setSearchParams]   = useSearchParams()
  const [activeTab, setActiveTab]         = useState("timeline")

  // Sync ?runId= query param
  const requestedRunId = searchParams.get("runId")
  useEffect(() => {
    if (requestedRunId && runs.some(r => r.run_id === requestedRunId) && requestedRunId !== selectedRunId) {
      setSelectedRunId(requestedRunId)
    }
  }, [requestedRunId, runs, selectedRunId, setSelectedRunId])

  // Data queries
  const summaryQuery = useRunSummaryQuery(selectedRunId)
  const runStatus    = summaryQuery.data?.status
  const eventsQuery  = useRunEventsQuery(selectedRunId, runStatus)
  const errorsQuery  = useRunErrorsQuery(selectedRunId)

  const errorCount   = errorsQuery.data?.total   ?? 0
  const pendingFiles = useQuery({
    queryKey: ["runs", selectedRunId, "files"],
    queryFn:  () => api.runs.files(selectedRunId),
    enabled:  Boolean(selectedRunId),
    refetchInterval: runStatus === "running" ? 3000 : false,
  }).data?.pending ?? 0

  // When a new run is selected reset to timeline tab
  useEffect(() => { setActiveTab("timeline") }, [selectedRunId])

  // Auto-switch to Errors tab when errors arrive and run has stopped
  useEffect(() => {
    if (runStatus && runStatus !== "running" && errorCount > 0 && activeTab === "timeline") {
      const t = setTimeout(() => setActiveTab("errors"), 1800)
      return () => clearTimeout(t)
    }
  }, [runStatus, errorCount, activeTab])

  const metaText = summaryQuery.isFetching
    ? "Refreshing…"
    : selectedRunId
      ? `${selectedRunId} · ${runStatus ?? "unknown"}`
      : "No run selected"

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.10),_transparent_28%),_linear-gradient(180deg,_#0f1117_0%,_#111827_100%)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">

        <PageHeader
          eyebrow="Monitor"
          title="Pipeline monitor"
          description="Live step-by-step timeline and structured error diagnostics for any pipeline run."
          meta={metaText}
          accentClass="text-sky-300/80"
        />

        <div className="grid gap-6 xl:grid-cols-[0.75fr_1.25fr]">

          {/* ── Left: run picker ──────────────────────────────── */}
          <div className="flex flex-col gap-4">
            <RunPicker
              title="Select a run"
              description="Choose a run to watch its live progress."
              runs={runs}
              selectedRunId={selectedRunId}
              onChange={(id) => {
                setSelectedRunId(id)
                setSearchParams(id ? { runId: id } : {})
              }}
              loading={runsQuery.isFetching}
            />

            {/* Live status card for selected run */}
            {selectedRunId && summaryQuery.data && (
              <SectionCard>
                <div className="px-5 py-4">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-300">Current status</span>
                    <LiveStatusBadge status={runStatus} />
                  </div>
                  <div className="space-y-1.5 text-xs text-slate-500">
                    <div>Story: <span className="text-slate-300">{summaryQuery.data.story_title || summaryQuery.data.story_id}</span></div>
                    <div>Started: <span className="text-slate-300">{formatDate(summaryQuery.data.started_at)}</span></div>
                    {summaryQuery.data.completed_at && (
                      <div>Finished: <span className="text-slate-300">{formatDate(summaryQuery.data.completed_at)}</span></div>
                    )}
                    {summaryQuery.data.all_gates_passed != null && (
                      <div>Gates: <span className={summaryQuery.data.all_gates_passed ? "text-emerald-400" : "text-rose-400"}>
                        {summaryQuery.data.all_gates_passed ? "All passed" : "Failed"}
                      </span></div>
                    )}
                    {summaryQuery.data.error && (
                      <div className="mt-2 rounded-xl border border-rose-500/20 bg-rose-500/8 p-2 text-rose-300">
                        {summaryQuery.data.error}
                      </div>
                    )}
                  </div>
                </div>
              </SectionCard>
            )}
          </div>

          {/* ── Right: tabbed content ─────────────────────────── */}
          <SectionCard className="flex flex-col overflow-hidden">
            {!selectedRunId ? (
              <div className="flex flex-1 items-center justify-center py-16">
                <EmptyState
                  icon="🔍"
                  title="No run selected"
                  subtitle="Pick a run from the left panel to start monitoring."
                />
              </div>
            ) : (
              <>
                {/* Run metrics strip */}
                <RunInfoStrip summary={summaryQuery.data} />

                {/* Tab navigation */}
                <TabBar active={activeTab} onChange={setActiveTab} errorCount={errorCount} pendingFiles={pendingFiles} runStatus={runStatus} />

                {/* Tab content */}
                <div className="flex-1 overflow-auto">
                  {activeTab === "timeline" && (
                    <TimelineTab
                      runId={selectedRunId}
                      runStatus={runStatus}
                      eventsQuery={eventsQuery}
                    />
                  )}
                  {activeTab === "errors" && (
                    <ErrorsTab
                      runId={selectedRunId}
                      runStatus={runStatus}
                      errorsQuery={errorsQuery}
                    />
                  )}
                  {activeTab === "files" && (
                    <FilesReviewTab
                      runId={selectedRunId}
                      runStatus={runStatus}
                    />
                  )}
                  {activeTab === "llmfix" && (
                    <LLMFixTab
                      runId={selectedRunId}
                      runStatus={runStatus}
                    />
                  )}
                </div>
              </>
            )}
          </SectionCard>

        </div>
      </div>
    </div>
  )
}
