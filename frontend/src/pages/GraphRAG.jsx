import { useRef, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Upload, RefreshCw, CheckCircle2, XCircle, AlertTriangle } from "lucide-react"
import SectionCard from "../components/SectionCard"
import PageHeader from "../components/PageHeader"
import { api } from "../lib/api"

function SourceBadge({ source, loaded }) {
  if (!loaded || !source) return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500">
      <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
      Not loaded
    </span>
  )
  if (source === "user") return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
      <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" />
      Loaded from user file
    </span>
  )
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
      Loaded from default context
    </span>
  )
}

export default function GraphRAG() {
  const queryClient = useQueryClient()
  const fileRef = useRef(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploadMsg, setUploadMsg] = useState(null)   // { type: "success"|"error", text }

  const summaryQuery = useQuery({ queryKey: ["graphrag", "summary"], queryFn: api.graphrag.summary })
  const statusQuery  = useQuery({ queryKey: ["graphrag", "status"],  queryFn: api.graphrag.status,
    refetchInterval: false })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["graphrag"] })
    queryClient.invalidateQueries({ queryKey: ["health"] })
  }

  const uploadMutation = useMutation({
    mutationFn: () => api.graphrag.upload(selectedFile),
    onSuccess: () => {
      setUploadMsg({ type: "success", text: "GraphRAG uploaded and loaded successfully." })
      setSelectedFile(null)
      if (fileRef.current) fileRef.current.value = ""
      invalidate()
    },
    onError: (err) => setUploadMsg({ type: "error", text: err.message || "Upload failed." }),
  })

  const defaultMutation = useMutation({
    mutationFn: api.graphrag.loadDefault,
    onSuccess: () => {
      setUploadMsg({ type: "success", text: "Default GraphRAG loaded successfully." })
      invalidate()
    },
    onError: (err) => setUploadMsg({ type: "error", text: err.message || "Failed to load default." }),
  })

  const data = summaryQuery.data
  const status = statusQuery.data
  const entities = data?.entities || []
  const relations = data?.relations || []

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="Knowledge graph"
          title="GraphRAG"
          description="Inspect the graph that was auto-loaded on backend startup: entities, relations, and bounded context."
          meta={summaryQuery.isFetching ? "Fetching graph summary..." : data?.loaded ? "Graph context active" : "No graph loaded"}
          accentClass="text-[#00AEEF]"
        />

        {/* ── Configuration section ─────────────────────────────────────────── */}
        <SectionCard>
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
            <div>
              <h2 className="text-lg font-medium text-slate-900">GraphRAG Configuration</h2>
              <p className="mt-1 text-sm text-slate-500">
                Upload your own GraphRAG JSON or restore the server default.
                <span className="ml-1 font-medium text-slate-700">Priority: user file &gt; server default &gt; not loaded.</span>
              </p>
            </div>
            <SourceBadge loaded={status?.loaded ?? data?.loaded} source={status?.source} />
          </div>

          <div className="space-y-4 px-6 py-5">
            {/* Upload row */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex-1">
                <label className="block text-xs font-medium text-slate-700 mb-1">GraphRAG JSON file</label>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".json"
                  onChange={(e) => { setSelectedFile(e.target.files[0] || null); setUploadMsg(null) }}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-1 file:text-xs file:font-semibold file:text-indigo-700 hover:file:bg-indigo-100"
                />
              </div>
              <button
                type="button"
                disabled={!selectedFile || uploadMutation.isPending}
                onClick={() => uploadMutation.mutate()}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 transition"
              >
                <Upload className="h-4 w-4" />
                {uploadMutation.isPending ? "Uploading…" : "Upload GraphRAG"}
              </button>
            </div>

            {/* Load default button */}
            <div className="flex items-center gap-3">
              <button
                type="button"
                disabled={defaultMutation.isPending}
                onClick={() => { setUploadMsg(null); defaultMutation.mutate() }}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 transition"
              >
                <RefreshCw className={`h-4 w-4 ${defaultMutation.isPending ? "animate-spin" : ""}`} />
                {defaultMutation.isPending ? "Loading…" : "Load default GraphRAG"}
              </button>
              <span className="text-xs text-slate-400">Restores the server-side default and clears any user upload.</span>
            </div>

            {/* Feedback banner */}
            {uploadMsg && (
              <div className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium ${
                uploadMsg.type === "success"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : "border-rose-200 bg-rose-50 text-rose-800"
              }`}>
                {uploadMsg.type === "success"
                  ? <CheckCircle2 className="h-4 w-4 shrink-0" />
                  : <XCircle className="h-4 w-4 shrink-0" />}
                {uploadMsg.text}
              </div>
            )}
          </div>
        </SectionCard>

        {summaryQuery.error ? (
          <SectionCard className="border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            {summaryQuery.error.message || "Failed to load GraphRAG summary"}
          </SectionCard>
        ) : null}

        <SectionCard>
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
            <div>
              <h2 className="text-lg font-medium text-slate-900">Graph summary</h2>
              <p className="mt-1 text-sm text-slate-500">Backend data from `/graphrag/summary`.</p>
            </div>
            <button
              type="button"
              onClick={() => queryClient.invalidateQueries({ queryKey: ["graphrag", "summary"] })}
              className="btn-secondary"
              disabled={summaryQuery.isFetching}
            >
              {summaryQuery.isFetching ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          <div className="space-y-4 px-6 py-5">
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="surface-muted rounded-3xl p-4">
                <div className="text-sm text-slate-500">Loaded status</div>
                <div className="mt-2 text-xl font-semibold text-slate-900">
                  {summaryQuery.isLoading ? "Loading..." : data?.loaded ? "Loaded" : "Not loaded"}
                </div>
              </div>
              <div className="surface-muted rounded-3xl p-4">
                <div className="text-sm text-slate-500">Entities</div>
                <div className="mt-2 text-xl font-semibold text-slate-900">{data?.entity_count ?? 0}</div>
              </div>
              <div className="surface-muted rounded-3xl p-4">
                <div className="text-sm text-slate-500">Relations</div>
                <div className="mt-2 text-xl font-semibold text-slate-900">{data?.relation_count ?? 0}</div>
              </div>
            </div>

            <div className="surface-muted rounded-3xl p-4">
              <div className="text-sm font-medium text-slate-900">Source file</div>
              <div className="mt-2 break-all text-sm text-slate-600">{data?.source_file || "No source file loaded."}</div>
            </div>

            <div className="surface-muted rounded-3xl p-4">
              <div className="text-sm font-medium text-slate-900">Entity types</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(data?.entity_types || []).length ? (
                  data.entity_types.map((type) => (
                    <span key={type} className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700">
                      {type}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-slate-500">No entity types available.</span>
                )}
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard>
          <div className="border-b border-slate-200 px-6 py-5">
            <h2 className="text-lg font-medium text-slate-900">Entities ({entities.length})</h2>
            <p className="mt-1 text-sm text-slate-500">Nodes extracted from the loaded GraphRAG file.</p>
          </div>
          <div className="px-6 py-5">
            {entities.length === 0 ? (
              <div className="text-sm text-slate-500">No entities to display.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Name</th>
                      <th className="px-3 py-2">Type</th>
                      <th className="px-3 py-2">Description</th>
                      <th className="px-3 py-2">Stories</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {entities.map((entity) => (
                      <tr key={entity.id} className="align-top">
                        <td className="px-3 py-2 font-medium text-slate-900">{entity.name}</td>
                        <td className="px-3 py-2">
                          <span className="rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-700">
                            {entity.type}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-600">{entity.description || "—"}</td>
                        <td className="px-3 py-2">
                          {entity.user_story_refs?.length ? (
                            <div className="flex flex-wrap gap-1">
                              {entity.user_story_refs.map((ref) => (
                                <span key={ref} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                                  {ref}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </SectionCard>

        <SectionCard>
          <div className="border-b border-slate-200 px-6 py-5">
            <h2 className="text-lg font-medium text-slate-900">Relations ({relations.length})</h2>
            <p className="mt-1 text-sm text-slate-500">Edges connecting entities in the knowledge graph.</p>
          </div>
          <div className="px-6 py-5">
            {relations.length === 0 ? (
              <div className="text-sm text-slate-500">No relations to display.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Source</th>
                      <th className="px-3 py-2">Relation</th>
                      <th className="px-3 py-2">Target</th>
                      <th className="px-3 py-2">Description</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {relations.map((relation, index) => (
                      <tr key={`${relation.source}-${relation.target}-${index}`} className="align-top">
                        <td className="px-3 py-2 font-medium text-slate-900">{relation.source}</td>
                        <td className="px-3 py-2">
                          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                            {relation.relation_type}
                          </span>
                        </td>
                        <td className="px-3 py-2 font-medium text-slate-900">{relation.target}</td>
                        <td className="px-3 py-2 text-slate-600">{relation.description || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </SectionCard>
      </div>
    </div>
  )
}
