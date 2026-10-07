import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../lib/api"

const STATUS_CFG = {
  pending: { badge: "border-sky-200 bg-sky-50 text-sky-700", dot: "bg-sky-500" },
  accepted: { badge: "border-emerald-200 bg-emerald-50 text-emerald-700", dot: "bg-emerald-500" },
  rejected: { badge: "border-rose-200 bg-rose-50 text-rose-700", dot: "bg-rose-500" },
}

function CommitBanner({ data, onCommit, committing }) {
  if (!data) return null
  const { all_approved, commit_allowed, pending, rejected, total, accepted } = data

  if (total === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
        No generated files found yet. Files will appear after the code generation step completes.
      </div>
    )
  }

  if (all_approved && commit_allowed) {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-emerald-700">Ready</span>
            <span className="text-sm font-medium text-emerald-700">
              All {total} file{total !== 1 ? "s" : ""} accepted. GitHub push can be triggered.
            </span>
          </div>
          <button
            type="button"
            onClick={onCommit}
            disabled={committing}
            className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-white px-4 py-2 text-sm font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {committing ? (
              <>
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-emerald-200 border-t-emerald-600" />
                Triggering GitHub Push...
              </>
            ) : (
              "Trigger GitHub Push"
            )}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3">
      <div className="text-sm">
        <span className="font-medium text-sky-700">GitHub push blocked</span>
        <span className="ml-1.5 text-sky-700/80">
          until all files are accepted
          {pending > 0 && ` · ${pending} pending`}
          {rejected > 0 && ` · ${rejected} rejected`}
          {` · ${accepted}/${total} accepted`}
        </span>
      </div>
    </div>
  )
}

function FileCard({ file, onAction }) {
  const [expanded, setExpanded] = useState(false)
  const cfg = STATUS_CFG[file.status] || STATUS_CFG.pending

  return (
    <div className={`rounded-2xl border overflow-hidden transition-all ${
      file.status === "accepted"
        ? "border-emerald-200"
        : file.status === "rejected"
          ? "border-rose-200"
          : "border-slate-200"
    } bg-white`}>
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className={`h-2 w-2 shrink-0 rounded-full ${cfg.dot}`} />
          <span className="truncate font-mono text-xs text-slate-700" title={file.path}>
            {file.path}
          </span>
        </div>

        <span className={`shrink-0 rounded-full border px-2.5 py-0.5 text-[11px] font-medium capitalize ${cfg.badge}`}>
          {file.status}
        </span>

        <span className="shrink-0 rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] text-slate-500">
          {file.language}
        </span>

        <div className="flex shrink-0 items-center gap-1.5">
          {file.status !== "accepted" ? (
            <button
              type="button"
              onClick={() => onAction(file.id, "accept")}
              className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 active:scale-95"
            >
              Accept
            </button>
          ) : null}
          {file.status !== "rejected" ? (
            <button
              type="button"
              onClick={() => onAction(file.id, "reject")}
              className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-medium text-rose-700 transition hover:bg-rose-100 active:scale-95"
            >
              Reject
            </button>
          ) : null}
          {file.status !== "pending" ? (
            <button
              type="button"
              onClick={() => onAction(file.id, "reset")}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1 text-[11px] text-slate-500 transition hover:bg-slate-50 active:scale-95"
              title="Reset to pending"
            >
              Reset
            </button>
          ) : null}
        </div>

        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="shrink-0 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-500 transition hover:bg-slate-100"
          title={expanded ? "Collapse" : "Show code"}
        >
          {expanded ? "Hide" : "Code"}
        </button>
      </div>

      {expanded ? (
        <div className="border-t border-slate-200">
          <pre className="max-h-96 overflow-auto bg-slate-950 p-4 font-mono text-[11px] leading-relaxed text-slate-100 whitespace-pre break-words">
            {file.content || "(empty file)"}
          </pre>
        </div>
      ) : null}
    </div>
  )
}

function SummaryBar({ data }) {
  if (!data || data.total === 0) return null
  const { total, accepted, pending, rejected } = data
  const pct = total > 0 ? Math.round((accepted / total) * 100) : 0

  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500">
      <span>{total} file{total !== 1 ? "s" : ""}</span>
      <span className="text-emerald-600">{accepted} accepted</span>
      <span className="text-sky-600">{pending} pending</span>
      <span className="text-rose-600">{rejected} rejected</span>
      <div className="min-w-[80px] flex-1">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full rounded-full bg-[linear-gradient(135deg,_#5B5CFF_0%,_#00AEEF_100%)] transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <span className="text-slate-500">{pct}%</span>
    </div>
  )
}

export default function FilesReviewTab({ runId, runStatus, pollMs = 3000 }) {
  const queryClient = useQueryClient()
  const [commitStatus, setCommitStatus] = useState(null)

  const filesQuery = useQuery({
    queryKey: ["runs", runId, "files"],
    queryFn: () => api.runs.files(runId),
    enabled: Boolean(runId),
    refetchInterval: runStatus === "running" ? pollMs : false,
  })

  const actionMutation = useMutation({
    mutationFn: ({ fileId, action }) => {
      if (action === "accept") return api.runs.acceptFile(runId, fileId)
      if (action === "reject") return api.runs.rejectFile(runId, fileId)
      return api.runs.resetFile(runId, fileId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs", runId, "files"] })
    },
  })

  async function handleCommit() {
    setCommitStatus("triggering")
    try {
      const response = await api.runs.triggerCommit(runId)
      setCommitStatus(response.status === "triggered" ? "done" : "error")
      if (response.status === "triggered") {
        queryClient.invalidateQueries({ queryKey: ["runs", runId] })
        queryClient.invalidateQueries({ queryKey: ["runs", runId, "events"] })
      }
    } catch {
      setCommitStatus("error")
    }
  }

  const data = filesQuery.data
  const files = data?.files || []

  return (
    <div className="space-y-4 px-6 py-5">
      {filesQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-200 border-t-slate-600" />
          Loading files...
        </div>
      ) : null}

      {filesQuery.error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {filesQuery.error.message}
        </div>
      ) : null}

      {actionMutation.error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm text-rose-700">
          {actionMutation.error.message}
        </div>
      ) : null}

      {commitStatus === "done" ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-700">
          Commit triggered. Check the Timeline tab for progress.
        </div>
      ) : null}

      {commitStatus === "error" ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm text-rose-700">
          Commit trigger failed. Check run status.
        </div>
      ) : null}

      {data ? (
        <CommitBanner
          data={data}
          onCommit={handleCommit}
          committing={commitStatus === "triggering"}
        />
      ) : null}

      {data && files.length > 0 ? <SummaryBar data={data} /> : null}

      {files.length > 0 ? (
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Bulk:</span>
          <button
            type="button"
            onClick={() => files.forEach((file) => file.status !== "accepted" && actionMutation.mutate({ fileId: file.id, action: "accept" }))}
            disabled={actionMutation.isPending || data?.all_approved}
            className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Accept all
          </button>
          <button
            type="button"
            onClick={() => files.forEach((file) => file.status !== "rejected" && actionMutation.mutate({ fileId: file.id, action: "reject" }))}
            disabled={actionMutation.isPending}
            className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Reject all
          </button>
          <button
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["runs", runId, "files"] })}
            className="ml-auto rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500 transition hover:bg-slate-50"
          >
            Refresh
          </button>
        </div>
      ) : null}

      {files.length > 0 ? (
        <div className="space-y-2">
          {files.map((file) => (
            <FileCard
              key={file.id}
              file={file}
              onAction={(fileId, action) => actionMutation.mutate({ fileId, action })}
            />
          ))}
        </div>
      ) : (
        !filesQuery.isLoading && data ? (
          <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-slate-200 bg-slate-50 py-10 text-center">
            <span className="text-sm font-medium text-slate-500">No generated files yet</span>
            <div className="text-xs text-slate-500">
              Files appear after the code generation step completes.
            </div>
          </div>
        ) : null
      )}
    </div>
  )
}
