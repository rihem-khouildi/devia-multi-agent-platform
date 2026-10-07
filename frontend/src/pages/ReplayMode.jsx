import { useEffect, useMemo, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import PageHeader from "../components/PageHeader"
import SectionCard from "../components/SectionCard"
import { api } from "../lib/api"
import { formatDate } from "../lib/format"
import { mapEventsToAgentMessages } from "../lib/agentCollaboration"

function ReplayBubble({ item, active }) {
  return (
    <div className={`rounded-[24px] border p-4 transition-all ${active ? "border-indigo-200 bg-indigo-50 shadow-[0_16px_40px_rgba(91,92,255,0.14)]" : "border-slate-200 bg-white"}`}>
      <div className="flex flex-wrap items-center gap-3">
        <div className={`flex h-10 w-10 items-center justify-center rounded-2xl text-xs font-semibold ${item.agent.accent}`}>
          {item.agent.avatar}
        </div>
        <div className="text-sm font-semibold text-slate-900">{item.agent.name}</div>
        <div className="text-xs text-slate-500">{formatDate(item.created_at)}</div>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-700">{item.message}</p>
    </div>
  )
}

export default function ReplayMode() {
  const { runId } = useParams()
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [cursor, setCursor] = useState(0)
  const timerRef = useRef(null)

  const eventsQuery = useQuery({
    queryKey: ["runs", runId, "replay-events"],
    queryFn: () => api.runs.events(runId),
    enabled: Boolean(runId),
  })

  const summaryQuery = useQuery({
    queryKey: ["runs", runId, "replay-summary"],
    queryFn: () => api.runs.get(runId),
    enabled: Boolean(runId),
  })

  const replayItems = useMemo(() => mapEventsToAgentMessages(eventsQuery.data?.events || []), [eventsQuery.data?.events])
  const visibleItems = replayItems.slice(0, cursor)
  const progress = replayItems.length ? Math.round((cursor / replayItems.length) * 100) : 0

  useEffect(() => {
    if (!isPlaying || replayItems.length === 0) return undefined
    if (cursor >= replayItems.length) {
      setIsPlaying(false)
      return undefined
    }

    timerRef.current = setTimeout(() => {
      setCursor((current) => Math.min(current + 1, replayItems.length))
    }, speed === 2 ? 500 : 1000)

    return () => clearTimeout(timerRef.current)
  }, [isPlaying, cursor, replayItems.length, speed])

  useEffect(() => {
    setCursor(replayItems.length > 0 ? 1 : 0)
    setIsPlaying(false)
  }, [runId, replayItems.length])

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <PageHeader
          eyebrow="Replay"
          title="Replay Mode"
          description="Animated playback of the recorded event stream for a selected run."
          meta={runId || "No run selected"}
          accentClass="text-[#5B5CFF]"
        />

        <div className="flex flex-wrap gap-3">
          <Link to="/history" className="btn-secondary">
            Back to history
          </Link>
          {runId ? (
            <Link to={`/pipeline/${runId}`} className="btn-secondary">
              Open pipeline
            </Link>
          ) : null}
        </div>

        <SectionCard>
          <div className="grid gap-4 border-b border-slate-200 px-6 py-5 lg:grid-cols-[1fr_auto] lg:items-center">
            <div>
              <div className="text-sm font-medium text-slate-900">Playback controls</div>
              <div className="mt-1 text-sm text-slate-500">
                {summaryQuery.data?.story_title || "Replay the event stream exactly as recorded by the backend."}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setIsPlaying(true)} disabled={replayItems.length === 0 || cursor >= replayItems.length} className="btn-primary">
                Play
              </button>
              <button type="button" onClick={() => setIsPlaying(false)} className="btn-secondary">
                Pause
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsPlaying(false)
                  setCursor(replayItems.length > 0 ? 1 : 0)
                }}
                className="btn-secondary"
              >
                Reset
              </button>
              <button type="button" onClick={() => setSpeed(1)} className={`rounded-xl border px-4 py-3 text-sm font-medium ${speed === 1 ? "border-indigo-200 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-600"}`}>
                x1
              </button>
              <button type="button" onClick={() => setSpeed(2)} className={`rounded-xl border px-4 py-3 text-sm font-medium ${speed === 2 ? "border-indigo-200 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-600"}`}>
                x2
              </button>
            </div>
          </div>

          <div className="space-y-5 px-6 py-5">
            <div>
              <div className="flex items-end justify-between gap-4">
                <div className="text-sm font-medium text-slate-900">Replay progress</div>
                <div className="text-2xl font-semibold text-slate-900">{progress}%</div>
              </div>
              <div className="mt-3 h-3 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-[linear-gradient(135deg,_#5B5CFF_0%,_#00AEEF_100%)] transition-all duration-500" style={{ width: `${progress}%` }} />
              </div>
            </div>

            {eventsQuery.isLoading ? <div className="text-sm text-slate-500">Loading replay events...</div> : null}

            {eventsQuery.error ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                {eventsQuery.error.message || "Failed to load replay events."}
              </div>
            ) : null}

            {!eventsQuery.isLoading && !eventsQuery.error && replayItems.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
                No events are available for replay on this run.
              </div>
            ) : null}

            {visibleItems.length > 0 ? (
              <div className="space-y-4">
                {visibleItems.map((item, index) => (
                  <ReplayBubble key={item.id} item={item} active={isPlaying && index === visibleItems.length - 1} />
                ))}
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>
    </div>
  )
}
