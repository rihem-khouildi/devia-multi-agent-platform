/**
 * ErrorCard — displays one structured compile or test error.
 *
 * Props
 * -----
 * error : RunStepError object from GET /runs/{id}/errors
 *   { step, error_type, summary, copyable_error, files[], raw_excerpt }
 */
import { useState } from "react"

// ── Error type metadata ───────────────────────────────────────────────────────

const ERROR_TYPE_META = {
  java_compilation_failure:              { label: "Java Compilation Failure",        accent: "rose",  icon: "⚠" },
  environment_or_dependency_failure:     { label: "Environment / Dependency Failure", accent: "amber", icon: "🔧" },
  maven_or_build_tool_failure:           { label: "Maven / Build Tool Failure",       accent: "amber", icon: "🔧" },
  maven_test_timeout:                    { label: "Maven Test Timeout",               accent: "amber", icon: "⏱" },
  test_assertion_failure:                { label: "Test Assertion Failure",           accent: "rose",  icon: "✗" },
  test_execution_failure:                { label: "Test Execution Error",             accent: "rose",  icon: "✗" },
  test_compilation_failure:              { label: "Test Compilation Failure",         accent: "rose",  icon: "⚠" },
  test_environment_or_dependency_failure:{ label: "Test Environment Failure",         accent: "amber", icon: "🔧" },
  test_tooling_failure:                  { label: "Test Tooling Failure",             accent: "amber", icon: "🔧" },
  missing_or_unreadable_test_report:     { label: "Missing Test Report",              accent: "amber", icon: "?" },
}

const STEP_LABEL = {
  compile:   "Compile",
  run_tests: "Run Tests",
}

function accentClasses(accent = "rose") {
  if (accent === "rose") return {
    border:  "border-rose-200",
    bg:      "bg-rose-50",
    badge:   "border-rose-200 bg-rose-100 text-rose-700",
    icon:    "text-rose-600",
    heading: "text-rose-700",
    divider: "border-rose-100",
  }
  return {
    border:  "border-sky-200",
    bg:      "bg-sky-50",
    badge:   "border-sky-200 bg-sky-100 text-sky-700",
    icon:    "text-sky-600",
    heading: "text-sky-700",
    divider: "border-sky-100",
  }
}

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  async function handle() {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const el = document.createElement("textarea")
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand("copy")
      document.body.removeChild(el)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={handle}
      className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-all hover:bg-slate-50 active:scale-95"
    >
      {copied
        ? <><span className="text-emerald-400">✓</span> Copied!</>
        : <><span>⎘</span> Copy error</>}
    </button>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ErrorCard({ error }) {
  const meta = ERROR_TYPE_META[error.error_type] ?? { label: error.error_type, accent: "rose", icon: "!" }
  const cls  = accentClasses(meta.accent)

  return (
    <div className={`rounded-2xl border ${cls.border} ${cls.bg} overflow-hidden`}>
      {/* Header */}
      <div className={`flex flex-wrap items-center justify-between gap-3 border-b ${cls.divider} px-5 py-4`}>
        <div className="flex items-center gap-3">
          <span className={`text-lg leading-none ${cls.icon}`}>{meta.icon}</span>
          <div>
            <div className="text-sm font-semibold text-slate-900">
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
        <p className="text-sm leading-relaxed text-slate-700">{error.summary}</p>

        {/* Affected files */}
        {error.files?.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">
              Affected files
            </p>
            <div className="space-y-1.5">
              {error.files.map((f, i) => (
                <div
                  key={`${f.path}-${f.line}-${i}`}
                  className="flex flex-wrap items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 font-mono text-xs"
                >
                  <span className="break-all text-[#5B5CFF]">{f.path}</span>
                  {f.line > 0 && (
                    <span className="shrink-0 rounded border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-[10px] text-sky-700">
                      line {f.line}
                    </span>
                  )}
                  <span className="break-all text-slate-600">{f.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recommended action (timeout / env failures) */}
        {error.recommended_action && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
            <span className="mr-1.5 font-semibold">Recommended action:</span>
            {error.recommended_action}
          </div>
        )}

        {/* Timeout diagnostics */}
        {error.timeout_details && (
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 font-mono text-xs text-slate-700 space-y-1">
            {error.timeout_details.timeout_seconds != null && (
              <div><span className="text-slate-400">timeout_seconds  </span>{error.timeout_details.timeout_seconds}</div>
            )}
            {error.timeout_details.duration_seconds != null && (
              <div><span className="text-slate-400">duration_seconds </span>{error.timeout_details.duration_seconds}</div>
            )}
            {error.timeout_details.exit_code != null && (
              <div><span className="text-slate-400">exit_code        </span>{error.timeout_details.exit_code}</div>
            )}
          </div>
        )}

        {/* No-source message for timeout */}
        {error.error_type === "maven_test_timeout" && (!error.files || error.files.length === 0) && (
          <p className="text-xs italic text-slate-500">
            No generated source file is directly responsible. This is an infrastructure or test execution timeout.
          </p>
        )}

        {/* Copyable error block */}
        {error.copyable_error && (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-500">
                Copy diagnostics
              </p>
              <CopyButton text={error.copyable_error} />
            </div>
            <pre className="max-h-52 overflow-auto rounded-xl border border-slate-200 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-100 whitespace-pre-wrap break-words">
              {error.copyable_error}
            </pre>
          </div>
        )}

        {/* Raw Maven excerpt (collapsed) */}
        {error.raw_excerpt && (
          <details className="group">
            <summary className="cursor-pointer select-none text-xs text-slate-500 hover:text-slate-700 transition-colors">
              <span className="group-open:hidden">▶ Show raw Maven output</span>
              <span className="hidden group-open:inline">▼ Hide raw Maven output</span>
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-xl border border-slate-200 bg-slate-950 p-4 font-mono text-[11px] leading-relaxed text-slate-200 whitespace-pre-wrap break-words">
              {error.raw_excerpt}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}
