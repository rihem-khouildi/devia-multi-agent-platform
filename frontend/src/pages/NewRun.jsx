import { useState, useRef } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import PageHeader from "../components/PageHeader"
import SectionCard from "../components/SectionCard"
import { api } from "../lib/api"

export default function NewRun() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Story input
  const [selectedStoryId, setSelectedStoryId] = useState("")
  const [freeText, setFreeText] = useState("")
  const [useStorySelect, setUseStorySelect] = useState(true)

  // Repo path (advanced override)
  const [selectedProjectPath, setSelectedProjectPath] = useState("")
  const [customPath, setCustomPath] = useState("")
  const [useCustomPath, setUseCustomPath] = useState(false)

  // ── Project source (Part 2) ──────────────────────────────────────────────
  const [sourceType, setSourceType] = useState("default") // "default" | "uploaded"
  const [selectedUploadedProject, setSelectedUploadedProject] = useState("")
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadStatus, setUploadStatus] = useState(null) // null | "uploading" | "success" | "error"
  const [uploadMessage, setUploadMessage] = useState("")
  const fileInputRef = useRef(null)

  const [dryRun, setDryRun] = useState(false)
  const [qualityMode, setQualityMode] = useState("demo")
  const [pushMode, setPushMode] = useState("approval_required")
  const [formError, setFormError] = useState("")

  // Fetch stories
  const { data: storiesData } = useQuery({
    queryKey: ["stories"],
    queryFn: api.stories.list,
    staleTime: 60_000,
  })
  const stories = storiesData?.stories ?? []

  // Fetch generated projects
  const { data: projectsData } = useQuery({
    queryKey: ["projects-generated"],
    queryFn: api.projects.generated,
    staleTime: 30_000,
  })
  const projects = projectsData?.projects ?? []
  const baseProject = projectsData?.base_project ?? null
  const pushedProjects = projects.filter((p) => p.github_pushed)
  const localProjects = projects.filter((p) => !p.github_pushed)

  // Fetch uploaded / source projects
  const { data: sourcesData, refetch: refetchSources } = useQuery({
    queryKey: ["project-sources"],
    queryFn: api.projectSources.list,
    staleTime: 30_000,
  })
  const uploadedProjects = (sourcesData?.sources ?? []).filter((s) => s.type === "uploaded")

  const createRunMutation = useMutation({
    mutationFn: api.runs.create,
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["runs"] })
      navigate(`/pipeline/${created.run_id}`)
    },
  })

  function getStoryInput() {
    return useStorySelect ? selectedStoryId.trim() : freeText.trim()
  }

  function getRepoPath() {
    if (useCustomPath) return customPath.trim()
    return selectedProjectPath.trim()
  }

  async function handleUpload() {
    if (!uploadFile) return
    setUploadStatus("uploading")
    setUploadMessage("")
    try {
      const result = await api.projectSources.upload(uploadFile)
      setUploadStatus("success")
      setUploadMessage(`Project "${result.name}" uploaded successfully.`)
      setSelectedUploadedProject(result.name)
      setUploadFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ""
      refetchSources()
    } catch (err) {
      setUploadStatus("error")
      setUploadMessage(err.message || "Upload failed.")
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    const storyInput = getStoryInput()
    if (!storyInput) {
      setFormError("Select an existing user story or enter a free-form request.")
      return
    }
    if (sourceType === "uploaded" && !selectedUploadedProject) {
      setFormError("Select an uploaded project or upload a new one first.")
      return
    }
    setFormError("")

    const payload = { story_input: storyInput, dry_run: dryRun }
    const repoPath = getRepoPath()
    if (repoPath) payload.repo_path = repoPath

    payload.source_project_type = sourceType
    if (sourceType === "uploaded") payload.source_project_name = selectedUploadedProject

    createRunMutation.mutate(payload)
  }

  const storyInputPreview = getStoryInput()
  const repoPathPreview = getRepoPath()

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
        <PageHeader
          eyebrow="Launch"
          title="New Run"
          description="Start a clean DEVIA run from a Jira story reference or a free-form requirement."
          meta={createRunMutation.isPending ? "Launching run..." : "Ready to launch"}
          accentClass="text-[#5B5CFF]"
        />

        <div className="flex flex-wrap gap-3">
          <Link to="/" className="btn-secondary">Back to dashboard</Link>
          <Link to="/history" className="btn-secondary">Open run history</Link>
        </div>

        {createRunMutation.error ? (
          <SectionCard className="border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            {createRunMutation.error.message || "Failed to start the run."}
          </SectionCard>
        ) : null}

        <SectionCard className="overflow-hidden">
          <div className="grid gap-6 px-6 py-6 lg:grid-cols-[1.15fr_0.85fr]">
            <form onSubmit={handleSubmit} className="space-y-5">

              {/* ── User Story ──────────────────────────────────────── */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-700">User Story</span>
                  <button
                    type="button"
                    onClick={() => { setUseStorySelect(!useStorySelect); setFormError("") }}
                    className="text-xs font-medium text-[#5B5CFF] hover:underline"
                  >
                    {useStorySelect ? "Enter free-form text instead" : "Select existing story"}
                  </button>
                </div>

                {useStorySelect ? (
                  <select
                    value={selectedStoryId}
                    onChange={(e) => { setSelectedStoryId(e.target.value); if (formError) setFormError("") }}
                    className="field-input"
                  >
                    <option value="">— Select an existing user story or paste a free-form feature request —</option>
                    {stories.map((s) => (
                      <option key={s.id} value={s.id}>[{s.id}] {s.title}</option>
                    ))}
                  </select>
                ) : (
                  <textarea
                    value={freeText}
                    onChange={(e) => { setFreeText(e.target.value); if (formError) setFormError("") }}
                    placeholder="Select an existing user story or paste a free-form feature request"
                    rows={5}
                    className="field-input resize-y"
                  />
                )}
              </div>

              {/* ── Project Source ──────────────────────────────────── */}
              <div>
                <span className="mb-2 block text-sm font-medium text-slate-700">Project Source</span>
                <div className="flex gap-3 mb-3">
                  <button
                    type="button"
                    onClick={() => setSourceType("default")}
                    className={`flex-1 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all ${
                      sourceType === "default"
                        ? "border-[#5B5CFF] bg-[rgba(91,92,255,0.08)] text-[#5B5CFF]"
                        : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                    }`}
                  >
                    Default base project
                  </button>
                  <button
                    type="button"
                    onClick={() => setSourceType("uploaded")}
                    className={`flex-1 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all ${
                      sourceType === "uploaded"
                        ? "border-[#5B5CFF] bg-[rgba(91,92,255,0.08)] text-[#5B5CFF]"
                        : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                    }`}
                  >
                    Custom / uploaded project
                  </button>
                </div>

                {sourceType === "default" && (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                    Using <strong>base-spring-project</strong> — the default Spring Boot base.
                  </div>
                )}

                {sourceType === "uploaded" && (
                  <div className="space-y-3">
                    {/* Existing uploaded projects */}
                    {uploadedProjects.length > 0 && (
                      <select
                        value={selectedUploadedProject}
                        onChange={(e) => setSelectedUploadedProject(e.target.value)}
                        className="field-input"
                      >
                        <option value="">— Select an uploaded project —</option>
                        {uploadedProjects.map((p) => (
                          <option key={p.name} value={p.name}>{p.name}</option>
                        ))}
                      </select>
                    )}

                    {/* Upload new zip */}
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <div className="mb-2 text-xs font-medium text-slate-600">Upload a new project (.zip)</div>
                      <div className="flex gap-2">
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept=".zip"
                          onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                          className="flex-1 text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-[#5B5CFF] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white"
                        />
                        <button
                          type="button"
                          disabled={!uploadFile || uploadStatus === "uploading"}
                          onClick={handleUpload}
                          className="rounded-xl bg-[#5B5CFF] px-4 py-2 text-xs font-medium text-white disabled:opacity-50"
                        >
                          {uploadStatus === "uploading" ? "Uploading…" : "Upload"}
                        </button>
                      </div>
                      {uploadMessage && (
                        <div className={`mt-2 text-xs ${uploadStatus === "error" ? "text-rose-600" : "text-emerald-600"}`}>
                          {uploadMessage}
                        </div>
                      )}
                    </div>

                    {uploadedProjects.length === 0 && !uploadMessage && (
                      <div className="text-xs text-slate-500">No uploaded projects yet. Upload a .zip above.</div>
                    )}
                  </div>
                )}
              </div>

              {/* ── Repository / Project (advanced) ─────────────────── */}
              <details className="group">
                <summary className="cursor-pointer list-none">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-700">Repository / Project <span className="text-xs text-slate-400">(advanced override)</span></span>
                    <button
                      type="button"
                      onClick={() => setUseCustomPath(!useCustomPath)}
                      className="text-xs font-medium text-[#5B5CFF] hover:underline"
                    >
                      {useCustomPath ? "Select from output folder" : "Enter custom path"}
                    </button>
                  </div>
                </summary>

                {useCustomPath ? (
                  <input
                    value={customPath}
                    onChange={(e) => setCustomPath(e.target.value)}
                    placeholder="C:\\Users\\msi\\Desktop\\my-project"
                    className="field-input"
                  />
                ) : (
                  <select
                    value={selectedProjectPath}
                    onChange={(e) => setSelectedProjectPath(e.target.value)}
                    className="field-input"
                  >
                    <option value="">— Select a base project —</option>
                    <optgroup label="Base Project">
                      {baseProject ? (
                        <option value={baseProject.path}>{baseProject.name}</option>
                      ) : (
                        <option value="">base-spring-project</option>
                      )}
                    </optgroup>
                    {pushedProjects.length > 0 && (
                      <optgroup label="Generated — Pushed to GitHub ✓">
                        {pushedProjects.map((p) => {
                          const val = p.base_path || p.path
                          return (
                            <option key={val} value={val}>
                              {p.name}{p.branch ? ` · ${p.branch}` : ""}{p.commit_sha ? ` · ${p.commit_sha.slice(0, 7)}` : ""}
                            </option>
                          )
                        })}
                      </optgroup>
                    )}
                    {localProjects.length > 0 && (
                      <optgroup label="Generated — Local only">
                        {localProjects.map((p) => (
                          <option key={p.path} value={p.path}>{p.name}</option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                )}
                <span className="mt-2 block text-xs text-slate-500">
                  Overrides the project source selection above.
                </span>
              </details>

              {/* ── Quality / Push mode ─────────────────────────────── */}
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate-700">Quality mode</span>
                  <select value={qualityMode} onChange={(e) => setQualityMode(e.target.value)} className="field-input">
                    <option value="demo">Demo</option>
                    <option value="strict">Strict</option>
                  </select>
                </label>
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate-700">Push mode</span>
                  <select value={pushMode} onChange={(e) => setPushMode(e.target.value)} className="field-input">
                    <option value="approval_required">Approval Required</option>
                    <option value="auto_publish">Auto Publish</option>
                  </select>
                </label>
              </div>

              {/* ── Dry run ─────────────────────────────────────────── */}
              <label className="surface-muted flex items-center gap-3 rounded-2xl px-4 py-3 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-[#5B5CFF] focus:ring-[#5B5CFF]/30"
                />
                <span>Dry run</span>
              </label>

              {formError ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {formError}
                </div>
              ) : null}

              <button type="submit" disabled={createRunMutation.isPending} className="btn-primary">
                {createRunMutation.isPending ? "Launching Devia Run..." : "Launch Devia Run"}
              </button>
            </form>

            {/* ── Summary panel ───────────────────────────────────── */}
            <div className="space-y-4">
              <div className="surface-muted rounded-3xl p-5">
                <div className="text-sm font-medium text-slate-900">Launch profile</div>
                <div className="mt-3 space-y-2 text-sm text-slate-600">
                  <div>Story: <span className="font-medium text-slate-900">{storyInputPreview || "—"}</span></div>
                  <div>Source: <span className="font-medium text-slate-900">
                    {sourceType === "default" ? "Default base project" : selectedUploadedProject ? `Uploaded: ${selectedUploadedProject}` : "Uploaded (none selected)"}
                  </span></div>
                  {repoPathPreview && (
                    <div>Repo override: <span className="font-medium text-slate-900 break-all">{repoPathPreview}</span></div>
                  )}
                  <div>Quality mode: <span className="font-medium text-slate-900">{qualityMode === "demo" ? "Demo" : "Strict"}</span></div>
                  <div>Push mode: <span className="font-medium text-slate-900">{pushMode === "approval_required" ? "Approval Required" : "Auto Publish"}</span></div>
                  <div>Dry run: <span className="font-medium text-slate-900">{dryRun ? "Enabled" : "Disabled"}</span></div>
                </div>
              </div>

              <div className="surface-muted rounded-3xl p-5">
                <div className="text-sm font-medium text-slate-900">What happens next</div>
                <div className="mt-3 space-y-2 text-sm text-slate-600">
                  <div>1. DEVIA creates the run through POST /runs.</div>
                  <div>2. The UI redirects to the live pipeline page for this run.</div>
                  <div>3. You can continue into Agent Collaboration, Replay and Quality Center.</div>
                </div>
              </div>
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  )
}
