import { Link, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import PageHeader from "../components/PageHeader"
import SectionCard from "../components/SectionCard"
import { api } from "../lib/api"
import { formatDate, statusTone, toneClasses } from "../lib/format"
import { mapEventsToAgentMessages } from "../lib/agentCollaboration"
import { buildPipelineStepStates } from "../lib/pipelineSteps"

function StatusBadge({ status }) {
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium capitalize ${toneClasses(statusTone(status))}`}>
      {status || "unknown"}
    </span>
  )
}

function AgentBubble({ item, isLast }) {
  return (
    <div className="relative flex gap-4">
      {!isLast ? <div className="absolute left-[23px] top-12 h-full w-px bg-slate-200" aria-hidden="true" /> : null}

      <div className={`relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl text-sm font-semibold shadow-sm ${item.agent.accent}`}>
        {item.agent.avatar}
      </div>

      <div className="min-w-0 flex-1 rounded-[24px] border border-slate-200 bg-white p-4 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
        <div className="flex flex-wrap items-center gap-3">
          <div className="text-sm font-semibold text-slate-900">{item.agent.name}</div>
          <StatusBadge status={item.status} />
          <div className="text-xs text-slate-500">{formatDate(item.created_at)}</div>
        </div>

        <p className="mt-3 text-sm leading-6 text-slate-700">{item.message}</p>

        {item.rawMessage && item.rawMessage !== item.message ? (
          <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
            Event source: {item.rawMessage}
          </div>
        ) : null}

        {item.details && Object.keys(item.details).length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(item.details).map(([key, value]) => {
              if (value == null || Array.isArray(value) || typeof value === "object") return null
              return (
                <span key={key} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] text-slate-600">
                  {key}: {String(value)}
                </span>
              )
            })}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function AgentSummary({ messages, stepStates }) {
  const agents = new Map()
  for (const message of messages) {
    agents.set(message.agent.name, (agents.get(message.agent.name) || 0) + 1)
  }

  const activeAgents = [...agents.entries()]
  const completedSteps = stepStates.filter((step) => ["success", "failed", "skipped"].includes(step.status)).length

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <div className="surface-muted rounded-3xl p-4">
        <div className="text-sm text-slate-500">Events translated</div>
        <div className="mt-2 text-2xl font-semibold text-slate-900">{messages.length}</div>
      </div>
      <div className="surface-muted rounded-3xl p-4">
        <div className="text-sm text-slate-500">Agents visible</div>
        <div className="mt-2 text-2xl font-semibold text-slate-900">{activeAgents.length}</div>
      </div>
      <div className="surface-muted rounded-3xl p-4">
        <div className="text-sm text-slate-500">Steps completed</div>
        <div className="mt-2 text-2xl font-semibold text-slate-900">{completedSteps}/{stepStates.length}</div>
      </div>
      <div className="surface-muted rounded-3xl p-4">
        <div className="text-sm text-slate-500">Most active</div>
        <div className="mt-2 text-sm font-semibold text-slate-900">
          {activeAgents.sort((a, b) => b[1] - a[1])[0]?.[0] || "No agent activity yet"}
        </div>
      </div>
    </div>
  )
}

export default function AgentCollaboration() {
  const { runId } = useParams()

  const summaryQuery = useQuery({
    queryKey: ["runs", runId, "agents-summary"],
    queryFn: () => api.runs.get(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  })

  const runStatus = summaryQuery.data?.status

  const eventsQuery = useQuery({
    queryKey: ["runs", runId, "agents-events"],
    queryFn: () => api.runs.events(runId),
    enabled: Boolean(runId),
    refetchInterval: runStatus === "running" ? 2000 : false,
  })

  const messages = mapEventsToAgentMessages(eventsQuery.data?.events || [])
  const stepStates = buildPipelineStepStates({
    summary: summaryQuery.data,
    events: eventsQuery.data?.events || [],
    files: null,
  })

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <PageHeader
          eyebrow="Multi-Agent"
          title="Agent Collaboration"
          description="Readable conversation view of how the pipeline agents coordinated on this run."
          meta={runId ? `${runId}${runStatus ? ` · ${runStatus}` : ""}` : "No run selected"}
          accentClass="text-[#00AEEF]"
        />

        <div className="flex flex-wrap gap-3">
          <Link to="/pipeline" className="btn-secondary">
            Back to runs
          </Link>
          {runId ? (
            <Link to={`/pipeline/${runId}`} className="btn-secondary">
              Open live pipeline
            </Link>
          ) : null}
        </div>

        {summaryQuery.error ? (
          <SectionCard className="border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
            {summaryQuery.error.message || "Failed to load run summary."}
          </SectionCard>
        ) : null}

        <AgentSummary messages={messages} stepStates={stepStates} />

        <SectionCard className="overflow-hidden">
          <div className="border-b border-slate-200 px-6 py-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-medium text-slate-900">Agent activity feed</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Messages are generated from real pipeline events returned by `GET /runs/{'{run_id}'}/events`.
                </p>
              </div>
              <StatusBadge status={runStatus} />
            </div>
          </div>

          <div className="space-y-5 px-6 py-6">
            {eventsQuery.isLoading ? (
              <div className="text-sm text-slate-500">Loading agent messages...</div>
            ) : null}

            {eventsQuery.error ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                {eventsQuery.error.message}
              </div>
            ) : null}

            {!eventsQuery.isLoading && !eventsQuery.error && messages.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
                No events were recorded yet for this run.
              </div>
            ) : null}

            {messages.map((item, index) => (
              <AgentBubble key={item.id} item={item} isLast={index === messages.length - 1} />
            ))}
          </div>
        </SectionCard>
      </div>
    </div>
  )
}
