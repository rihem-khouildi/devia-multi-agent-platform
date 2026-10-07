import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  Activity,
  CheckCircle2,
  XCircle,
  FolderGit2,
  Database,
  GitBranch,
  Brain,
  Layers,
  Ticket,
  ArrowRight,
  Clock,
  Rocket,
  Settings,
} from "lucide-react"
import { api } from "../lib/api"

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(dateStr) {
  if (!dateStr) return "N/A"
  return new Date(dateStr).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function statusColor(status) {
  const s = String(status || "").toLowerCase()
  if (["success", "completed", "done"].includes(s))
    return { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", dot: "bg-emerald-500" }
  if (["failed", "error"].includes(s))
    return { bg: "bg-rose-50", border: "border-rose-200", text: "text-rose-700", dot: "bg-rose-500" }
  if (["running", "in_progress", "pending"].includes(s))
    return { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700", dot: "bg-blue-500" }
  return { bg: "bg-slate-50", border: "border-slate-200", text: "text-slate-600", dot: "bg-slate-400" }
}

function StatusBadge({ status }) {
  const c = statusColor(status)
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${c.bg} ${c.border} ${c.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {status || "unknown"}
    </span>
  )
}

// ── Top Stat Card ─────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, description, iconBg, iconColor }) {
  return (
    <div className="flex items-start gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${iconBg}`}>
        <Icon className={`h-5 w-5 ${iconColor}`} />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-widest text-slate-400">{label}</p>
        <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
        <p className="mt-0.5 text-xs text-slate-500">{description}</p>
      </div>
    </div>
  )
}

// ── Health Row ────────────────────────────────────────────────────────────────

function HealthRow({ icon: Icon, label, description, status, ok }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white border border-slate-200">
          <Icon className="h-4 w-4 text-slate-600" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-900">{label}</p>
          <p className="text-xs text-slate-500 truncate">{description}</p>
        </div>
      </div>
      <span className={`shrink-0 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        ok
          ? "bg-emerald-50 border-emerald-200 text-emerald-700"
          : "bg-slate-100 border-slate-200 text-slate-500"
      }`}>
        <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-500" : "bg-slate-400"}`} />
        {status}
      </span>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()

  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: api.runs.list,
    staleTime: 30_000,
  })

  const generatedQuery = useQuery({
    queryKey: ["projects-generated"],
    queryFn: api.projects.generated,
    staleTime: 60_000,
  })

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    staleTime: 30_000,
    retry: false,
  })

  // ── Derived stats ──────────────────────────────────────────────────────────
  const runs = runsQuery.data?.runs ?? []
  const totalRuns = runs.length
  const successRuns = runs.filter((r) => ["success", "completed", "done"].includes(String(r.status).toLowerCase())).length
  const failedRuns = runs.filter((r) => ["failed", "error"].includes(String(r.status).toLowerCase())).length

  const generatedProjects = Array.isArray(generatedQuery.data)
    ? generatedQuery.data.length
    : generatedQuery.data?.projects?.length ?? generatedQuery.data?.count ?? 0

  // ── Latest run ────────────────────────────────────────────────────────────
  const latestRun = runs.length > 0
    ? [...runs].sort((a, b) => {
        const da = new Date(a.finished_at || a.started_at || a.created_at || 0)
        const db = new Date(b.finished_at || b.started_at || b.created_at || 0)
        return db - da
      })[0]
    : null

  // ── Health data ───────────────────────────────────────────────────────────
  const health = healthQuery.data

  // Resolve Jira/GitHub label based on source field
  function resolveServiceStatus(serviceHealth, labels) {
    const source = serviceHealth?.source
    const configured = serviceHealth?.configured
    if (!configured) return { ok: false, status: "Not configured" }
    if (source === "user") return { ok: true, status: "Configured by user" }
    return { ok: true, status: labels?.env ?? "Connected" }
  }

  const jiraStatus = resolveServiceStatus(health?.config?.jira, { env: "Connected" })
  const githubStatus = resolveServiceStatus(health?.config?.github, { env: "Ready" })

  const healthServices = [
    {
      icon: Ticket,
      label: "Jira Connection",
      description: "User stories import service",
      ok: jiraStatus.ok,
      status: jiraStatus.status,
    },
    {
      icon: GitBranch,
      label: "GitHub Integration",
      description: "Commit and pull request service",
      ok: githubStatus.ok,
      status: githubStatus.status,
    },
    {
      icon: Layers,
      label: "GraphRAG Context",
      description: "Knowledge context injection",
      ok: Boolean(health?.config?.graphrag?.loaded),
      status: (() => {
        const src = health?.config?.graphrag?.source
        if (!health?.config?.graphrag?.loaded) return "Not loaded"
        if (src === "user") return "Loaded from user file"
        return "Loaded"
      })(),
    },
    {
      icon: Brain,
      label: "LLM Provider",
      description: "Code generation models (Hugging Face)",
      ok: Boolean(health?.config?.huggingface?.configured ?? (health?.status === "ok")),
      status: Boolean(health?.config?.huggingface?.configured ?? (health?.status === "ok")) ? "Available" : "Not available",
    },
    {
      icon: Database,
      label: "Database",
      description: "Pipeline persistence layer",
      ok: Boolean(health?.database?.ready),
      status: Boolean(health?.database?.ready) ? "Connected" : "Disconnected",
    },
  ]

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">

        {/* ── Page Header ─────────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-slate-200 bg-white px-6 py-6 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-indigo-700">
                <Activity className="h-3.5 w-3.5" />
                Dashboard
              </div>
              <h1 className="mt-3 text-2xl font-bold text-slate-900">Devia Overview</h1>
              <p className="mt-1 text-sm text-slate-500">
                Monitor pipeline executions, generated projects and service health.
              </p>
            </div>
            <button
              type="button"
              onClick={() => navigate("/pipeline")}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 transition"
            >
              <Rocket className="h-4 w-4" />
              New Pipeline Run
            </button>
          </div>
        </div>

        {/* ── Top Cards ───────────────────────────────────────────────────── */}
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            icon={Activity}
            label="Total Runs"
            value={runsQuery.isLoading ? "…" : totalRuns}
            description="All pipeline executions"
            iconBg="bg-indigo-50"
            iconColor="text-indigo-600"
          />
          <StatCard
            icon={CheckCircle2}
            label="Successful Runs"
            value={runsQuery.isLoading ? "…" : successRuns}
            description="Completed successfully"
            iconBg="bg-emerald-50"
            iconColor="text-emerald-600"
          />
          <StatCard
            icon={XCircle}
            label="Failed Runs"
            value={runsQuery.isLoading ? "…" : failedRuns}
            description="Runs requiring attention"
            iconBg="bg-rose-50"
            iconColor="text-rose-600"
          />
          <StatCard
            icon={FolderGit2}
            label="Generated Projects"
            value={generatedQuery.isLoading ? "…" : generatedProjects}
            description="Available generated projects"
            iconBg="bg-amber-50"
            iconColor="text-amber-600"
          />
        </div>

        {/* ── Bottom Grid ─────────────────────────────────────────────────── */}
        <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">

          {/* Latest Pipeline Execution */}
          <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-base font-semibold text-slate-900">Latest Pipeline Execution</h2>
              <p className="mt-0.5 text-xs text-slate-500">Most recent run based on execution date</p>
            </div>

            <div className="px-6 py-5">
              {runsQuery.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
                  Loading run data…
                </div>
              ) : !latestRun ? (
                <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-5 py-8 text-center">
                  <Activity className="mx-auto h-8 w-8 text-slate-300" />
                  <p className="mt-3 text-sm font-medium text-slate-600">No pipeline execution found.</p>
                  <p className="mt-1 text-xs text-slate-400">Start a new run to see execution details here.</p>
                  <button
                    type="button"
                    onClick={() => navigate("/pipeline")}
                    className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 transition"
                  >
                    <Rocket className="h-3.5 w-3.5" />
                    Start a run
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Story & Status */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-medium uppercase tracking-widest text-slate-400">User Story</p>
                      <p className="mt-1 truncate text-sm font-semibold text-slate-900">
                        {latestRun.story_title || latestRun.story_id || "—"}
                      </p>
                      <p className="mt-0.5 font-mono text-xs text-slate-400">{latestRun.run_id}</p>
                    </div>
                    <StatusBadge status={latestRun.status} />
                  </div>

                  {/* Metrics grid */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                      <p className="text-xs text-slate-500">Review Score</p>
                      <p className="mt-1 text-lg font-bold text-slate-900">
                        {latestRun.review_score != null ? `${latestRun.review_score}/100` : "N/A"}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                      <p className="text-xs text-slate-500">Quality Gate</p>
                      <p className={`mt-1 text-lg font-bold ${
                        latestRun.quality_gate_passed === true ? "text-emerald-600"
                        : latestRun.quality_gate_passed === false ? "text-rose-600"
                        : "text-slate-900"
                      }`}>
                        {latestRun.quality_gate_passed === true ? "Passed"
                          : latestRun.quality_gate_passed === false ? "Failed"
                          : "N/A"}
                      </p>
                    </div>
                  </div>

                  {/* Date */}
                  <div className="flex items-center gap-1.5 text-xs text-slate-500">
                    <Clock className="h-3.5 w-3.5" />
                    {latestRun.finished_at
                      ? `Finished at ${formatDate(latestRun.finished_at)}`
                      : latestRun.started_at
                      ? `Started at ${formatDate(latestRun.started_at)}`
                      : `Created at ${formatDate(latestRun.created_at)}`}
                  </div>

                  {/* View details */}
                  <button
                    type="button"
                    onClick={() => navigate(`/pipeline/${latestRun.run_id}`)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 transition"
                  >
                    View details
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Pipeline Health */}
          <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Pipeline Health</h2>
                <p className="mt-0.5 text-xs text-slate-500">Status of services required by the pipeline</p>
              </div>
              <button
                type="button"
                onClick={() => navigate("/integrations")}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 transition"
              >
                <Settings className="h-3.5 w-3.5" />
                Configure
              </button>
            </div>
            <div className="px-6 py-5">
              {healthQuery.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
                  Checking services…
                </div>
              ) : (
                <div className="space-y-2.5">
                  {healthServices.map((svc) => (
                    <HealthRow key={svc.label} {...svc} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
