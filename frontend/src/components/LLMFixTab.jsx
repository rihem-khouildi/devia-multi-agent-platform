/**
 * LLMFixTab — AI-driven error correction for failed pipeline runs.
 *
 * Shows current errors, lets the user pick a target (compile / tests / both),
 * launches an LLM fix, polls for status, then displays the result.
 * No GitHub push is triggered at any point.
 */
import { useState, useEffect, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../lib/api"

// ── Small helpers ─────────────────────────────────────────────────────────────

function Spinner({ label = "Processing…" }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-400">
      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-violet-400" />
      {label}
    </div>
  )
}

function Badge({ children, tone = "default" }) {
  const styles = {
    default: "border-white/10 bg-white/5 text-slate-300",
    success: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    danger:  "border-rose-400/30 bg-rose-400/10 text-rose-300",
    warning: "border-amber-400/30 bg-amber-400/10 text-amber-300",
    violet:  "border-violet-400/30 bg-violet-400/10 text-violet-300",
    running: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${styles[tone]}`}>
      {children}
    </span>
  )
}

function StatusIcon({ status }) {
  if (status === "success") return <span className="text-emerald-400 text-lg">✓</span>
  if (status === "failed")  return <span className="text-rose-400 text-lg">✗</span>
  if (status === "running") return (
    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-violet-400" />
  )
  return <span className="text-slate-500 text-lg">○</span>
}

// ── Target selector ───────────────────────────────────────────────────────────

const TARGET_OPTIONS = [
  { value: "compile",   label: "Compile only",     desc: "Re-run mvn compile after patch" },
  { value: "run_tests", label: "Tests only",        desc: "Re-run mvn test after patch" },
  { value: "both",      label: "Compile + Tests",   desc: "Full validation after patch" },
]

function TargetSelect({ value, onChange, disabled }) {
  return (
    <div className="flex flex-wrap gap-2">
      {TARGET_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          disabled={disabled}
          onClick={() => onChange(opt.value)}
          title={opt.desc}
          className={`rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
            value === opt.value
              ? "border-violet-400/50 bg-violet-400/15 text-violet-200"
              : "border-white/10 bg-white/5 text-slate-400 hover:border-white/20 hover:text-slate-200"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// ── Error summary (read-only, collapsible) ────────────────────────────────────

function ErrorSummary({ errors }) {
  const [open, setOpen] = useState(true)
  if (!errors || errors.length === 0) return null
  return (
    <div className="rounded-2xl border border-rose-400/20 bg-rose-400/5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-rose-300">
          <span>✗</span>
          {errors.length} error block{errors.length !== 1 ? "s" : ""} detected
        </span>
        <span className="text-xs text-slate-500">{open ? "▲ hide" : "▼ show"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-rose-400/10 px-4 pb-4 pt-3">
          {errors.map((err, i) => (
            <div key={i} className="rounded-xl border border-white/5 bg-white/3 p-3">
              <div className="mb-1 flex items-center gap-2">
                <Badge tone="danger">{err.step}</Badge>
                <span className="text-xs text-slate-400">{err.error_type}</span>
              </div>
              <p className="text-xs text-rose-200">{err.summary}</p>
              {err.files?.slice(0, 3).map((f, j) => (
                <p key={j} className="mt-1 font-mono text-[10px] text-slate-500">
                  {f.path}:{f.line} — {f.message}
                </p>
              ))}
              {err.files?.length > 3 && (
                <p className="mt-1 text-[10px] text-slate-600">+{err.files.length - 3} more…</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Result panel ──────────────────────────────────────────────────────────────

function ResultPanel({ status }) {
  if (!status || status.status === "idle") return null

  const isRunning  = status.status === "running"
  const isSuccess  = status.status === "success"
  const isFailed   = status.status === "failed"

  const res = status.last_result

  return (
    <div className={`rounded-2xl border p-4 ${
      isRunning ? "border-sky-400/20 bg-sky-400/5"
      : isSuccess ? "border-emerald-400/20 bg-emerald-400/5"
      : "border-rose-400/20 bg-rose-400/5"
    }`}>
      {/* Header */}
      <div className="mb-3 flex items-center gap-3">
        <StatusIcon status={status.status} />
        <div className="flex-1">
          <p className={`text-sm font-medium ${
            isRunning ? "text-sky-200" : isSuccess ? "text-emerald-200" : "text-rose-200"
          }`}>
            {status.message}
          </p>
          {status.started_at && (
            <p className="text-[10px] text-slate-500 mt-0.5">
              Started {new Date(status.started_at).toLocaleTimeString()}
              {status.completed_at && ` · Finished ${new Date(status.completed_at).toLocaleTimeString()}`}
            </p>
          )}
        </div>
        {isRunning && (
          <Badge tone="running">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400" />
            Running
          </Badge>
        )}
        {isSuccess && <Badge tone="success">Fixed</Badge>}
        {isFailed && !isRunning && <Badge tone="danger">Failed</Badge>}
      </div>

      {/* Rollback notice */}
      {isFailed && status.message?.includes("Original files restored") && (
        <div className="mb-3 flex items-center gap-2 rounded-xl border border-amber-400/20 bg-amber-400/5 px-3 py-2">
          <span className="text-amber-400 text-sm">↺</span>
          <p className="text-xs text-amber-300">
            Patch did not fix the issue — original files have been automatically restored.
          </p>
        </div>
      )}

      {/* Auto-escalation notice */}
      {status.message?.includes("compile + tests") || status.patched_files?.length > 0 && isFailed && !status.message?.includes("Original files restored") ? null : null}

      {/* Patched files */}
      {status.patched_files?.length > 0 && !status.message?.includes("Original files restored") && (
        <div className="mb-3">
          <p className="mb-1.5 text-xs font-medium text-slate-400">Modified files:</p>
          <div className="space-y-1">
            {status.patched_files.map((f) => (
              <div key={f} className="flex items-center gap-2 font-mono text-[11px] text-slate-300">
                <span className="text-violet-400">~</span>
                {f}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Validation result */}
      {res && (
        <div className="mt-2 flex flex-wrap gap-2 border-t border-white/5 pt-3">
          {res.compile_ok != null && (
            <div className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium ${
              res.compile_ok
                ? "border-emerald-400/30 bg-emerald-400/8 text-emerald-300"
                : "border-rose-400/30 bg-rose-400/8 text-rose-300"
            }`}>
              {res.compile_ok ? "✓" : "✗"} Compile
            </div>
          )}
          {res.tests_ok != null && (
            <div className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium ${
              res.tests_ok
                ? "border-emerald-400/30 bg-emerald-400/8 text-emerald-300"
                : "border-rose-400/30 bg-rose-400/8 text-rose-300"
            }`}>
              {res.tests_ok ? "✓" : "✗"} Tests
            </div>
          )}
          {res.test_coverage != null && (
            <div className="flex items-center gap-1.5 rounded-lg border border-sky-400/30 bg-sky-400/8 px-2.5 py-1 text-xs font-medium text-sky-300">
              Coverage {res.test_coverage?.toFixed(1)}%
            </div>
          )}
        </div>
      )}

      {/* Still-failing tests */}
      {res?.failed_tests?.length > 0 && (
        <div className="mt-3 rounded-xl border border-rose-400/10 bg-rose-400/5 p-3">
          <p className="mb-1 text-xs font-medium text-rose-300">Still failing tests:</p>
          {res.failed_tests.slice(0, 6).map((t) => (
            <p key={t} className="font-mono text-[10px] text-rose-400">{t}</p>
          ))}
          {res.failed_tests.length > 6 && (
            <p className="text-[10px] text-slate-500">+{res.failed_tests.length - 6} more…</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function LLMFixTab({ runId, runStatus }) {
  const queryClient = useQueryClient()
  const [target, setTarget] = useState("both")

  // Current errors
  const errorsQuery = useQuery({
    queryKey:  ["runs", runId, "errors"],
    queryFn:   () => api.runs.errors(runId),
    enabled:   Boolean(runId),
    staleTime: 5000,
  })

  // LLM fix status — poll while running
  const fixQuery = useQuery({
    queryKey:       ["runs", runId, "llm-fix-status"],
    queryFn:        () => api.runs.llmFixStatus(runId),
    enabled:        Boolean(runId),
    refetchInterval: (query) => query.state.data?.status === "running" ? 2000 : false,
  })

  const fixStatus = fixQuery.data
  const isFixRunning = fixStatus?.status === "running"

  // Invalidate errors after a successful fix so the badge updates
  useEffect(() => {
    if (fixStatus?.status === "success" || fixStatus?.status === "failed") {
      queryClient.invalidateQueries({ queryKey: ["runs", runId, "errors"] })
    }
  }, [fixStatus?.status, runId, queryClient])

  // Trigger mutation
  const launchMutation = useMutation({
    mutationFn: () => api.runs.llmFix(runId, { mode: "auto", target }),
    onSuccess: () => {
      // Start polling immediately
      queryClient.invalidateQueries({ queryKey: ["runs", runId, "llm-fix-status"] })
    },
  })

  const canFix = Boolean(runId)
    && runStatus !== "running"
    && !isFixRunning
    && !launchMutation.isPending

  const errors = errorsQuery.data?.errors ?? []
  const hasErrors = errors.length > 0

  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["runs", runId, "errors"] })
    queryClient.invalidateQueries({ queryKey: ["runs", runId, "llm-fix-status"] })
  }, [runId, queryClient])

  return (
    <div className="space-y-5 px-6 py-5">

      {/* Header description */}
      <div className="rounded-2xl border border-violet-400/15 bg-violet-400/5 px-4 py-3">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 text-xl">🤖</span>
          <div>
            <p className="text-sm font-medium text-violet-200">AI-Powered Error Fix</p>
            <p className="mt-0.5 text-xs text-slate-400">
              The LLM analyses your compile/test errors and produces a minimal targeted patch.
              Files are corrected locally — no GitHub push is triggered.
            </p>
          </div>
        </div>
      </div>

      {/* Current errors */}
      {errorsQuery.isLoading && <Spinner label="Loading errors…" />}

      {!errorsQuery.isLoading && !hasErrors && (
        <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/5 px-4 py-4">
          <div className="flex items-center gap-2.5">
            <span className="text-xl text-emerald-400">✓</span>
            <div>
              <p className="text-sm font-semibold text-emerald-200">No errors to fix</p>
              <p className="mt-0.5 text-xs text-emerald-400/70">
                {runStatus === "running"
                  ? "Pipeline is still running…"
                  : "No compile or test failures recorded for this run."}
              </p>
            </div>
          </div>
        </div>
      )}

      {hasErrors && <ErrorSummary errors={errors} />}

      {/* Target selector */}
      {hasErrors && (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-widest text-slate-500">
            Re-run target after patch
          </p>
          <TargetSelect value={target} onChange={setTarget} disabled={!canFix} />
          {target === "run_tests" && (
            <p className="text-[10px] text-slate-500">
              ℹ If the code does not compile yet, the target will automatically escalate to "Compile + Tests".
            </p>
          )}
        </div>
      )}

      {/* Launch button */}
      {hasErrors && (
        <div className="flex items-center gap-3 flex-wrap">
          <button
            disabled={!canFix}
            onClick={() => launchMutation.mutate()}
            className={`flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-all
              ${canFix
                ? "bg-violet-600 text-white hover:bg-violet-500 shadow-lg shadow-violet-500/25"
                : "cursor-not-allowed bg-white/5 text-slate-500"}
            `}
          >
            {launchMutation.isPending || isFixRunning ? (
              <>
                <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                {launchMutation.isPending ? "Launching…" : "LLM working…"}
              </>
            ) : (
              <>
                <span>✦</span>
                Ask LLM to Fix
              </>
            )}
          </button>

          <button
            onClick={handleRefresh}
            className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            ↻ Refresh
          </button>

          {launchMutation.isError && (
            <p className="text-xs text-rose-400">
              {launchMutation.error?.message || "Failed to launch fix."}
            </p>
          )}
        </div>
      )}

      {/* Result panel */}
      {fixQuery.data && <ResultPanel status={fixQuery.data} />}

      {/* Tip when no errors and no fix ever run */}
      {!hasErrors && !fixQuery.data && !errorsQuery.isLoading && (
        <p className="text-xs text-slate-600 text-center pt-2">
          Run a pipeline first — if it fails, errors will appear here and you can trigger an LLM fix.
        </p>
      )}
    </div>
  )
}
