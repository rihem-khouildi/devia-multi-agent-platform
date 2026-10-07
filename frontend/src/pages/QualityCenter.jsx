import { useState, useMemo } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ShieldCheck,
  Star,
  TestTube2,
  Hammer,
  BarChart3,
  ChevronDown,
} from "lucide-react"
import PageHeader from "../components/PageHeader"
import SectionCard from "../components/SectionCard"
import { api } from "../lib/api"

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(d) {
  if (!d) return ""
  return new Date(d).toLocaleDateString("fr-FR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  })
}

function clamp(v, min = 0, max = 100) {
  return Math.min(max, Math.max(min, Number(v) || 0))
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MetricCard({ icon: Icon, label, value, badge, description, iconBg, iconColor }) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${iconBg}`}>
          <Icon className={`h-5 w-5 ${iconColor}`} />
        </div>
        {badge}
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-widest text-slate-400">{label}</p>
        <p className="mt-1 text-2xl font-bold text-slate-900">{value ?? "N/A"}</p>
        {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
      </div>
    </div>
  )
}

function StatusBadge({ ok, label }) {
  if (ok === true)
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        {label || "Passed"}
      </span>
    )
  if (ok === false)
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-rose-50 px-2.5 py-0.5 text-xs font-medium text-rose-700">
        <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
        {label || "Failed"}
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-500">
      <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
      {label || "N/A"}
    </span>
  )
}

function ProgressBar({ value, max = 100, colorClass = "bg-indigo-500", threshold }) {
  const pct = clamp((value / max) * 100)
  const aboveThreshold = threshold != null ? value >= threshold : true
  const bar = aboveThreshold ? colorClass : "bg-rose-500"
  return (
    <div className="mt-2 h-2 w-full rounded-full bg-slate-100">
      <div
        className={`h-2 rounded-full transition-all duration-500 ${bar}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function GateItem({ ok, label }) {
  const Icon = ok ? CheckCircle2 : XCircle
  return (
    <div className={`flex items-center gap-3 rounded-xl border px-4 py-2.5 ${
      ok
        ? "border-emerald-100 bg-emerald-50"
        : "border-rose-100 bg-rose-50"
    }`}>
      <Icon className={`h-4 w-4 shrink-0 ${ok ? "text-emerald-600" : "text-rose-600"}`} />
      <span className={`text-sm font-medium ${ok ? "text-emerald-800" : "text-rose-800"}`}>{label}</span>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function QualityCenter() {
  const [selectedRunId, setSelectedRunId] = useState(null)

  // All runs for the selector
  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: api.runs.list,
    staleTime: 30_000,
  })
  const runs = runsQuery.data?.runs ?? []

  // Auto-select the latest run
  const latestRunId = useMemo(() => {
    if (!runs.length) return null
    return [...runs].sort((a, b) => {
      const da = new Date(a.finished_at || a.started_at || a.created_at || 0)
      const db = new Date(b.finished_at || b.started_at || b.created_at || 0)
      return db - da
    })[0]?.run_id ?? null
  }, [runs])

  const activeRunId = selectedRunId ?? latestRunId

  const qualityQuery = useQuery({
    queryKey: ["runs", activeRunId, "quality"],
    queryFn: () => api.runs.quality(activeRunId),
    enabled: Boolean(activeRunId),
  })

  const summaryQuery = useQuery({
    queryKey: ["runs", activeRunId, "summary"],
    queryFn: () => api.runs.get(activeRunId),
    enabled: Boolean(activeRunId),
  })

  const quality = qualityQuery.data
  const summary = summaryQuery.data

  // ── Derived metrics ───────────────────────────────────────────────────────
  const compileOk = summary?.compile_success ?? null
  const testsOk   = quality?.gates?.tests_success ?? null
  const coverageRaw = summary?.test_coverage ?? quality?.metrics?.test_coverage ?? null
  const coverageNum = coverageRaw != null ? parseFloat(String(coverageRaw).replace("%", "")) : null
  const reviewScore = summary?.review_score ?? quality?.metrics?.review_score ?? null
  const gatesPassed = quality?.passed ?? null

  // Gate criteria items
  const gateCriteria = [
    { ok: compileOk === true,         label: "Compilation completed successfully" },
    { ok: testsOk === true,           label: "Unit tests executed and passed" },
    { ok: coverageNum != null && coverageNum >= 35, label: `Coverage threshold reached (${coverageNum != null ? `${coverageNum}%` : "N/A"} / min 35%)` },
    { ok: reviewScore != null && reviewScore >= 70, label: `Review score accepted (${reviewScore != null ? `${reviewScore}/100` : "N/A"} / min 70)` },
  ]

  const selectedRun = runs.find((r) => r.run_id === activeRunId)

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="Quality"
          title="Quality Metrics"
          description="Analyse the quality results of a pipeline run: compilation, tests, coverage, review score and quality gate."
          meta={activeRunId || "No run selected"}
          accentClass="text-[#5B5CFF]"
        />

        <div className="flex flex-wrap gap-3">
          <Link to="/history" className="btn-secondary">Back to history</Link>
          {activeRunId && (
            <Link to={`/pipeline/${activeRunId}`} className="btn-secondary">Open pipeline monitor</Link>
          )}
        </div>

        {/* ── Run Selector ─────────────────────────────────────────────────── */}
        <SectionCard className="p-5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
            <label htmlFor="run-select" className="shrink-0 text-sm font-medium text-slate-700">
              Select Run:
            </label>
            <div className="relative flex-1 max-w-lg">
              <select
                id="run-select"
                value={activeRunId ?? ""}
                onChange={(e) => setSelectedRunId(e.target.value || null)}
                className="w-full appearance-none rounded-xl border border-slate-200 bg-white py-2.5 pl-4 pr-10 text-sm text-slate-900 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              >
                {runsQuery.isLoading && <option>Loading runs…</option>}
                {!runsQuery.isLoading && runs.length === 0 && <option>No runs available</option>}
                {runs.map((r) => {
                  const s = String(r.status || "").toLowerCase()
                  const statusLabel = ["success", "completed", "done"].includes(s) ? "Success"
                    : ["failed", "error"].includes(s) ? "Failed"
                    : r.status || "Unknown"
                  const date = r.finished_at || r.started_at || r.created_at
                  return (
                    <option key={r.run_id} value={r.run_id}>
                      {r.story_id || r.story_title || r.run_id} — {statusLabel}{date ? ` — ${formatDate(date)}` : ""}
                    </option>
                  )
                })}
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            </div>
            {selectedRun && (
              <span className="text-xs text-slate-500">
                Run ID: <span className="font-mono font-medium">{selectedRun.run_id}</span>
              </span>
            )}
          </div>
        </SectionCard>

        {/* ── Empty state ───────────────────────────────────────────────────── */}
        {!activeRunId && !runsQuery.isLoading && (
          <SectionCard className="p-10 text-center">
            <BarChart3 className="mx-auto h-10 w-10 text-slate-300" />
            <p className="mt-3 text-sm font-medium text-slate-600">No quality metrics available.</p>
            <p className="mt-1 text-xs text-slate-400">Run a pipeline to generate quality results.</p>
          </SectionCard>
        )}

        {activeRunId && (
          <>
            {/* ── Metric Cards ──────────────────────────────────────────────── */}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
              <MetricCard
                icon={Hammer}
                label="Compilation"
                value={compileOk === null ? "N/A" : compileOk ? "Success" : "Failed"}
                badge={<StatusBadge ok={compileOk} label={compileOk === null ? "N/A" : compileOk ? "Passed" : "Failed"} />}
                description="mvn compile result"
                iconBg={compileOk ? "bg-emerald-50" : compileOk === false ? "bg-rose-50" : "bg-slate-100"}
                iconColor={compileOk ? "text-emerald-600" : compileOk === false ? "text-rose-600" : "text-slate-500"}
              />
              <MetricCard
                icon={TestTube2}
                label="Tests Status"
                value={testsOk === null ? "N/A" : testsOk ? "Passed" : "Failed"}
                badge={<StatusBadge ok={testsOk} label={testsOk === null ? "N/A" : testsOk ? "Passed" : "Failed"} />}
                description="mvn test execution"
                iconBg={testsOk ? "bg-emerald-50" : testsOk === false ? "bg-rose-50" : "bg-slate-100"}
                iconColor={testsOk ? "text-emerald-600" : testsOk === false ? "text-rose-600" : "text-slate-500"}
              />
              <MetricCard
                icon={BarChart3}
                label="Code Coverage"
                value={coverageNum != null ? `${coverageNum}%` : "N/A"}
                badge={<StatusBadge ok={coverageNum != null ? coverageNum >= 35 : null} label={coverageNum != null ? (coverageNum >= 35 ? "OK" : "Low") : "N/A"} />}
                description="JaCoCo line coverage"
                iconBg="bg-blue-50"
                iconColor="text-blue-600"
              />
              <MetricCard
                icon={Star}
                label="Review Score"
                value={reviewScore != null ? `${reviewScore}/100` : "N/A"}
                badge={<StatusBadge ok={reviewScore != null ? reviewScore >= 70 : null} label={reviewScore != null ? (reviewScore >= 70 ? "Accepted" : "Low") : "N/A"} />}
                description="LLM code review score"
                iconBg="bg-yellow-50"
                iconColor="text-yellow-600"
              />
              <MetricCard
                icon={ShieldCheck}
                label="Quality Gate"
                value={gatesPassed === null ? "N/A" : gatesPassed ? "Passed" : "Failed"}
                badge={<StatusBadge ok={gatesPassed} label={gatesPassed === null ? "N/A" : gatesPassed ? "Passed" : "Failed"} />}
                description="GitHub push authorization"
                iconBg={gatesPassed ? "bg-emerald-50" : gatesPassed === false ? "bg-rose-50" : "bg-slate-100"}
                iconColor={gatesPassed ? "text-emerald-600" : gatesPassed === false ? "text-rose-600" : "text-slate-500"}
              />
            </div>

            {/* ── Progress Bars + Gate Summary ──────────────────────────────── */}
            <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">

              {/* Progress Bars */}
              <SectionCard className="p-6">
                <h2 className="text-base font-semibold text-slate-900">Quality Metrics Progress</h2>
                <p className="mt-0.5 text-xs text-slate-500">Numeric metrics compared to minimum thresholds</p>

                <div className="mt-5 space-y-6">
                  {/* Coverage */}
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-700">Code Coverage</span>
                      <span className="text-sm font-bold text-slate-900">
                        {coverageNum != null ? `${coverageNum}%` : "N/A"}
                      </span>
                    </div>
                    {coverageNum != null ? (
                      <>
                        <ProgressBar
                          value={coverageNum}
                          colorClass="bg-blue-500"
                          threshold={35}
                        />
                        <div className="mt-1 flex justify-between text-xs text-slate-400">
                          <span>0%</span>
                          <span className="text-slate-500">Min: 35%</span>
                          <span>100%</span>
                        </div>
                      </>
                    ) : (
                      <div className="mt-2 h-2 rounded-full bg-slate-100" />
                    )}
                  </div>

                  {/* Review Score */}
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-700">Review Score</span>
                      <span className="text-sm font-bold text-slate-900">
                        {reviewScore != null ? `${reviewScore}/100` : "N/A"}
                      </span>
                    </div>
                    {reviewScore != null ? (
                      <>
                        <ProgressBar
                          value={reviewScore}
                          colorClass="bg-yellow-500"
                          threshold={70}
                        />
                        <div className="mt-1 flex justify-between text-xs text-slate-400">
                          <span>0</span>
                          <span className="text-slate-500">Min: 70</span>
                          <span>100</span>
                        </div>
                      </>
                    ) : (
                      <div className="mt-2 h-2 rounded-full bg-slate-100" />
                    )}
                  </div>

                  {/* Run context */}
                  <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-xs text-slate-600 space-y-1">
                    <div><span className="font-medium text-slate-700">Story:</span> {summary?.story_title || summary?.story_id || "N/A"}</div>
                    <div><span className="font-medium text-slate-700">Status:</span> {summary?.status || "N/A"}</div>
                    <div><span className="font-medium text-slate-700">Commit SHA:</span> {summary?.commit_sha || "N/A"}</div>
                  </div>
                </div>
              </SectionCard>

              {/* Quality Gate Summary */}
              <SectionCard className="p-6">
                <h2 className="text-base font-semibold text-slate-900">Quality Gate Summary</h2>
                <p className="mt-0.5 text-xs text-slate-500">Criteria evaluated before authorizing GitHub push</p>

                {qualityQuery.isLoading ? (
                  <div className="mt-5 flex items-center gap-2 text-sm text-slate-500">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
                    Loading quality data…
                  </div>
                ) : qualityQuery.error ? (
                  <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                    {qualityQuery.error.message || "Failed to load quality data."}
                  </div>
                ) : (
                  <>
                    <div className="mt-5 space-y-2.5">
                      {gateCriteria.map((item) => (
                        <GateItem key={item.label} ok={item.ok} label={item.label} />
                      ))}
                    </div>

                    {/* Overall result banner */}
                    <div className={`mt-5 flex items-center gap-3 rounded-xl border px-4 py-3 ${
                      gatesPassed === true
                        ? "border-emerald-200 bg-emerald-50"
                        : gatesPassed === false
                        ? "border-rose-200 bg-rose-50"
                        : "border-slate-200 bg-slate-50"
                    }`}>
                      {gatesPassed === true
                        ? <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" />
                        : gatesPassed === false
                        ? <XCircle className="h-5 w-5 shrink-0 text-rose-600" />
                        : <AlertTriangle className="h-5 w-5 shrink-0 text-slate-400" />
                      }
                      <span className={`text-sm font-semibold ${
                        gatesPassed === true ? "text-emerald-800"
                        : gatesPassed === false ? "text-rose-800"
                        : "text-slate-600"
                      }`}>
                        {gatesPassed === true
                          ? "Quality gate passed — code is ready for GitHub push."
                          : gatesPassed === false
                          ? "Quality gate failed — resolve the issues above before pushing."
                          : "Quality gate result not yet available."}
                      </span>
                    </div>
                  </>
                )}
              </SectionCard>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
