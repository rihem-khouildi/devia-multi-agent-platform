import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import PageHeader from "../components/PageHeader"
import RunPicker from "../components/RunPicker"
import SectionCard from "../components/SectionCard"
import { useDefaultRunId, useRunsQuery, useRunErrorsQuery } from "../lib/runQueries"

// ── Labels & colours per error_type ─────────────────────────────────────────

const ERROR_TYPE_META = {
  java_compilation_failure: {
    label: "Java Compilation Failure",
    accent: "rose",
    icon: "⚠",
  },
  environment_or_dependency_failure: {
    label: "Environment / Dependency Failure",
    accent: "amber",
    icon: "🔧",
  },
  maven_or_build_tool_failure: {
    label: "Maven / Build Tool Failure",
    accent: "amber",
    icon: "🔧",
  },
  test_assertion_failure: {
    label: "Test Assertion Failure",
    accent: "rose",
    icon: "✗",
  },
  test_execution_failure: {
    label: "Test Execution Error",
    accent: "rose",
    icon: "✗",
  },
  test_compilation_failure: {
    label: "Test Compilation Failure",
    accent: "rose",
    icon: "⚠",
  },
  test_environment_or_dependency_failure: {
    label: "Test Environment Failure",
    accent: "amber",
    icon: "🔧",
  },
  test_tooling_failure: {
    label: "Test Tooling Failure",
    accent: "amber",
    icon: "🔧",
  },
  missing_or_unreadable_test_report: {
    label: "Missing Test Report",
    accent: "amber",
    icon: "?",
  },
}

const STEP_LABEL = {
  compile: "Compile",
  run_tests: "Run Tests",
}

function accentClasses(accent = "rose") {
  return accent === "rose"
    ? {
        border: "border-rose-500/30",
        bg: "bg-rose-500/8",
        badge: "border-rose-400/30 bg-rose-400/10 text-rose-300",
        icon: "text-rose-400",
        heading: "text-rose-200",
      }
    : {
        border: "border-amber-500/30",
        bg: "bg-amber-500/8",
        badge: "border-amber-400/30 bg-amber-400/10 text-amber-300",
        icon: "text-amber-400",
        heading: "text-amber-200",
      }
}

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text, className = "" }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback for non-secure contexts
      const el = document.createElement("textarea")
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand("copy")
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <button
      onClick={handleCopy}
      className={`flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 transition-all hover:border-white/20 hover:bg-white/10 hover:text-white active:scale-95 ${className}`}
    >
      {copied ? (
        <>
          <span className="text-emerald-400">✓</span>
          Copied!
        </>
      ) : (
        <>
          <span>⎘</span>
          Copy error
        </>
      )}
    </button>
  )
}

// ── File location row ─────────────────────────────────────────────────────────

function FileEntry({ file }) {
  return (
    <div className="flex flex-wrap items-start gap-2 rounded-xl border border-white/8 bg-[#0f1420] px-3 py-2.5 font-mono text-xs">
      <span className="text-sky-300 break-all">{file.path}</span>
      {file.line > 0 && (
        <span className="shrink-0 rounded border border-sky-400/20 bg-sky-400/10 px-1.5 py-0.5 text-[10px] text-sky-400">
          line {file.line}
        </span>
      )}
      <span className="text-slate-300 break-all">{file.message}</span>
    </div>
  )
}

// ── Single error card ─────────────────────────────────────────────────────────

function ErrorCard({ error }) {
  const meta = ERROR_TYPE_META[error.error_type] || {
    label: error.error_type,
    accent: "rose",
    icon: "!",
  }
  const cls = accentClasses(meta.accent)

  return (
    <div className={`rounded-2xl border ${cls.border} ${cls.bg} overflow-hidden`}>
      {/* Card header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/8 px-5 py-4">
        <div className="flex items-center gap-3">
          <span className={`text-lg leading-none ${cls.icon}`}>{meta.icon}</span>
          <div>
            <div className="text-sm font-semibold text-white">
              {STEP_LABEL[error.step] ?? error.step}
            </div>
            <div className={`mt-0.5 text-xs ${cls.heading}`}>{meta.label}</div>
          </div>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${cls.badge}`}>
          {error.step}
        </span>
      </div>

      <div className="space-y-4 px-5 py-4">
        {/* Summary */}
        <p className="text-sm leading-relaxed text-slate-200">{error.summary}</p>

        {/* File locations */}
        {error.files && error.files.length > 0 && (
          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">
              Affected files
            </div>
            <div className="space-y-1.5">
              {error.files.map((f, i) => (
                <FileEntry key={`${f.path}-${f.line}-${i}`} file={f} />
              ))}
            </div>
          </div>
        )}

        {/* Copyable error block */}
        {error.copyable_error && (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <div className="text-xs font-medium uppercase tracking-wider text-slate-500">
                Copy / paste
              </div>
              <CopyButton text={error.copyable_error} />
            </div>
            <pre className="max-h-52 overflow-auto rounded-xl border border-white/10 bg-[#0d0f14] p-4 font-mono text-xs leading-relaxed text-slate-200 whitespace-pre-wrap break-words">
              {error.copyable_error}
            </pre>
          </div>
        )}

        {/* Raw excerpt (collapsed by default) */}
        {error.raw_excerpt && (
          <details className="group">
            <summary className="cursor-pointer select-none text-xs text-slate-500 hover:text-slate-400 transition-colors">
              <span className="group-open:hidden">▶ Show raw Maven output</span>
              <span className="hidden group-open:inline">▼ Hide raw Maven output</span>
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-xl border border-white/8 bg-[#0d0f14] p-4 font-mono text-[11px] leading-relaxed text-slate-400 whitespace-pre-wrap break-words">
              {error.raw_excerpt}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function RunErrors() {
  const runsQuery = useRunsQuery()
  const runs = runsQuery.data?.runs || []
  const [selectedRunId, setSelectedRunId] = useDefaultRunId(runs)
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedRunId = searchParams.get("runId")

  useEffect(() => {
    if (
      requestedRunId &&
      runs.some((r) => r.run_id === requestedRunId) &&
      requestedRunId !== selectedRunId
    ) {
      setSelectedRunId(requestedRunId)
    }
  }, [requestedRunId, runs, selectedRunId, setSelectedRunId])

  const errorsQuery = useRunErrorsQuery(selectedRunId)
  const errors = errorsQuery.data?.errors || []
  const total = errorsQuery.data?.total ?? 0

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(244,63,94,0.10),_transparent_28%),_linear-gradient(180deg,_#0f1117_0%,_#111827_100%)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="Diagnostics"
          title="Run errors"
          description="Structured compilation and test failures — readable, copyable, and ready to fix."
          meta={
            errorsQuery.isFetching
              ? "Refreshing errors..."
              : selectedRunId
              ? `${total} error${total !== 1 ? "s" : ""} · ${selectedRunId}`
              : "No run selected"
          }
          accentClass="text-rose-300/80"
        />

        <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
          {/* ── Run picker ────────────────────────────────── */}
          <RunPicker
            title="Inspect a run"
            description="Select a run to load its compile and test errors."
            runs={runs}
            selectedRunId={selectedRunId}
            onChange={(runId) => {
              setSelectedRunId(runId)
              setSearchParams(runId ? { runId } : {})
            }}
            loading={runsQuery.isFetching}
          />

          {/* ── Error panel ───────────────────────────────── */}
          <SectionCard>
            <div className="border-b border-white/10 px-6 py-5">
              <h2 className="text-lg font-medium text-white">Error details</h2>
              <p className="mt-1 text-sm text-slate-400">
                Compile and test failures from{" "}
                <code className="rounded bg-white/8 px-1.5 py-0.5 text-xs text-slate-300">
                  GET /runs/{"{run_id}"}/errors
                </code>
              </p>
            </div>

            <div className="space-y-5 px-6 py-5">
              {/* Loading */}
              {errorsQuery.isLoading && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/20 border-t-white/80" />
                  Loading errors…
                </div>
              )}

              {/* API error */}
              {errorsQuery.error && (
                <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
                  {errorsQuery.error.message || "Failed to load errors"}
                </div>
              )}

              {/* No run selected */}
              {!selectedRunId && !errorsQuery.isLoading && (
                <div className="rounded-2xl border border-white/8 bg-white/3 p-6 text-center text-sm text-slate-500">
                  Select a run from the left panel.
                </div>
              )}

              {/* No errors */}
              {errorsQuery.data && total === 0 && (
                <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/8 p-5">
                  <div className="flex items-center gap-2">
                    <span className="text-lg text-emerald-400">✓</span>
                    <div>
                      <div className="text-sm font-semibold text-emerald-200">No errors recorded</div>
                      <div className="mt-0.5 text-xs text-emerald-400/70">
                        The pipeline completed without compile or test failures, or the run is still
                        in progress.
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Error cards */}
              {errors.map((error, i) => (
                <ErrorCard key={`${error.step}-${i}`} error={error} />
              ))}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
