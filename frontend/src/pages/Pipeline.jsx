import { useState, useRef } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  BookOpen,
  Network,
  ListTodo,
  Code2,
  Hammer,
  TestTube2,
  Play,
  Star,
  ShieldCheck,
  GitPullRequest,
} from "lucide-react"
import CompactStoryCard from "../components/CompactStoryCard"
import PageHeader from "../components/PageHeader"
import SectionCard from "../components/SectionCard"
import TargetProjectCard from "../components/TargetProjectCard"
import { api } from "../lib/api"

function badgeClasses(tone = "neutral") {
  if (tone === "success") return "border-emerald-200 bg-emerald-50 text-emerald-700"
  if (tone === "danger") return "border-rose-200 bg-rose-50 text-rose-700"
  if (tone === "accent") return "border-indigo-200 bg-indigo-50 text-indigo-700"
  return "border-slate-200 bg-slate-50 text-slate-600"
}

function statusTone(value) {
  const normalized = String(value || "").toUpperCase()
  if (["AVAILABLE", "LOADED", "PASS", "VALIDATED", "SELECTED"].includes(normalized)) return "success"
  if (["FAIL", "FAILED", "NOT LOADED", "UNAVAILABLE"].includes(normalized)) return "danger"
  return "neutral"
}

function StatusBadge({ value }) {
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium ${badgeClasses(statusTone(value))}`}>
      {value}
    </span>
  )
}

export default function Pipeline() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // ── Existing states ───────────────────────────────────────────────────────
  const [selectedProject, setSelectedProject] = useState(null)
  const [selectedStory, setSelectedStory] = useState(null)

  // ── Project source states (Part 2) ────────────────────────────────────────
  const [sourceProjectType, setSourceProjectType] = useState("default")   // "default" | "uploaded"
  const [sourceProjectName, setSourceProjectName] = useState(null)         // name of selected uploaded project
  const [selectedFile, setSelectedFile] = useState(null)
  const [loadingUpload, setLoadingUpload] = useState(false)
  const [uploadStatus, setUploadStatus] = useState(null)   // null | "success" | "error"
  const [uploadMessage, setUploadMessage] = useState("")
  const fileInputRef = useRef(null)

  // ── Queries ───────────────────────────────────────────────────────────────
  const storiesQuery = useQuery({
    queryKey: ["stories"],
    queryFn: api.stories.list,
    staleTime: 60_000,
  })
  const graphSummaryQuery = useQuery({
    queryKey: ["graphrag-summary"],
    queryFn: api.graphrag.summary,
    staleTime: 30_000,
  })
  const sourcesQuery = useQuery({
    queryKey: ["project-sources"],
    queryFn: api.projectSources.list,
    staleTime: 30_000,
  })
  const uploadedProjects = (sourcesQuery.data?.sources ?? []).filter((s) => s.type === "uploaded")

  // ── Mutations ─────────────────────────────────────────────────────────────
  const createRunMutation = useMutation({
    mutationFn: api.startRun,
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["runs"] })
      navigate(`/pipeline/${created.run_id}`)
    },
  })

  // ── Derived state ─────────────────────────────────────────────────────────
  const stories = storiesQuery.data?.stories || []
  const graphLoaded = Boolean(graphSummaryQuery.data?.loaded)
  const projectValidated = selectedProject?.validation?.overall_status === "VALIDATED"

  const canRun = Boolean(
    selectedStory &&
    !createRunMutation.isPending &&
    (
      (sourceProjectType === "default" && selectedProject && projectValidated) ||
      (sourceProjectType === "uploaded" && sourceProjectName)
    )
  )

  // ── Handlers ──────────────────────────────────────────────────────────────
  async function handleUpload() {
    if (!selectedFile) return
    setLoadingUpload(true)
    setUploadStatus(null)
    setUploadMessage("")
    try {
      const result = await api.projectSources.upload(selectedFile)
      setUploadStatus("success")
      setUploadMessage(`Project "${result.name}" uploaded successfully.`)
      setSourceProjectName(result.name)
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ""
      queryClient.invalidateQueries({ queryKey: ["project-sources"] })
    } catch (err) {
      setUploadStatus("error")
      setUploadMessage(err.message || "Upload failed. Please try again.")
    } finally {
      setLoadingUpload(false)
    }
  }

  function handleSelectSourceType(type) {
    setSourceProjectType(type)
    setUploadStatus(null)
    setUploadMessage("")
  }

  function handleRun() {
    if (!selectedStory) return

    // Validation: uploaded type requires a project name
    if (sourceProjectType === "uploaded" && !sourceProjectName) return

    const body = {
      story_input: selectedStory.id,
      dry_run: true,
      source_project_type: sourceProjectType,
      source_project_name: sourceProjectType === "uploaded" ? sourceProjectName : null,
    }

    // Pass target_project_path only for the default flow (keeps TargetProjectCard validation relevant)
    if (sourceProjectType === "default" && selectedProject?.path) {
      body.target_project_path = selectedProject.path
    }

    createRunMutation.mutate(body)
  }

  // ── Source display label for Step 3 summary ───────────────────────────────
  const sourceLabel = sourceProjectType === "uploaded"
    ? (sourceProjectName ? `Uploaded: ${sourceProjectName}` : "Custom project (none selected)")
    : (selectedProject?.name || "Base Spring Project (default)")

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <PageHeader
          eyebrow="Execution"
          title="AI-SDLC Pipeline Execution"
          description="Select a target Spring Boot project, choose a Jira user story, then launch the generation pipeline."
          meta={createRunMutation.isPending ? "Starting pipeline..." : "Demo flow ready"}
          accentClass="text-[#5B5CFF]"
        />

        <div className="flex flex-wrap gap-3">
          <Link to="/history" className="btn-secondary">Run History</Link>
          <Link to="/projects" className="btn-secondary">Generated Outputs</Link>
        </div>

        {createRunMutation.error ? (
          <SectionCard className="border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            {createRunMutation.error.message || "Failed to start run."}
          </SectionCard>
        ) : null}

        {/* ── STEP 1 — Select Target Project ─────────────────────────────── */}
        <SectionCard className="p-6">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-[#5B5CFF]">Step 1</div>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">Select Target Project</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Choose the Spring Boot source repository the pipeline will analyze before generating new output.
            Use the default base project or import your own.
          </p>

          {/* ── Two-option selector ──────────────────────────────────────── */}
          <div className="mt-5 grid gap-4 lg:grid-cols-2">

            {/* Card 1 — Base Spring Project */}
            <div
              className={`flex flex-col rounded-3xl border-2 transition-all ${
                sourceProjectType === "default"
                  ? "border-[#5B5CFF] shadow-[0_0_0_4px_rgba(91,92,255,0.08)]"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              {/* Card header */}
              <div className={`flex items-center justify-between rounded-t-3xl px-5 py-4 ${
                sourceProjectType === "default" ? "bg-[rgba(91,92,255,0.05)]" : "bg-slate-50"
              }`}>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.22em] text-[#5B5CFF]">Default</div>
                  <div className="mt-1 text-base font-semibold text-slate-900">Base Spring Project</div>
                </div>
                {sourceProjectType === "default" && (
                  <span className="rounded-full border border-[#5B5CFF] bg-[rgba(91,92,255,0.08)] px-3 py-1 text-xs font-medium text-[#5B5CFF]">
                    Selected
                  </span>
                )}
              </div>

              {/* Card body — TargetProjectCard handles fetch + validation */}
              <div className="flex-1 px-1 pb-2">
                <TargetProjectCard
                  selectedProject={sourceProjectType === "default" ? selectedProject : null}
                  onSelect={(proj) => {
                    setSelectedProject(proj)
                    setSourceProjectType("default")
                  }}
                  useButtonLabel="Use Base Project"
                />
              </div>
            </div>

            {/* Card 2 — Import Custom Project */}
            <div
              className={`flex flex-col rounded-3xl border-2 transition-all ${
                sourceProjectType === "uploaded"
                  ? "border-[#00AEEF] shadow-[0_0_0_4px_rgba(0,174,239,0.08)]"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              {/* Card header */}
              <div className={`flex items-center justify-between rounded-t-3xl px-5 py-4 ${
                sourceProjectType === "uploaded" ? "bg-[rgba(0,174,239,0.05)]" : "bg-slate-50"
              }`}>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.22em] text-[#00AEEF]">Custom</div>
                  <div className="mt-1 text-base font-semibold text-slate-900">Import Custom Project</div>
                </div>
                {sourceProjectType === "uploaded" && sourceProjectName && (
                  <span className="rounded-full border border-[#00AEEF] bg-[rgba(0,174,239,0.08)] px-3 py-1 text-xs font-medium text-[#00AEEF]">
                    Selected
                  </span>
                )}
              </div>

              {/* Card body */}
              <div className="flex flex-1 flex-col gap-4 px-5 py-4">
                <p className="text-sm text-slate-500">
                  Upload your own Spring Boot project as a ZIP file, or select a previously uploaded one.
                </p>

                {/* Upload new zip */}
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                    Upload new project (.zip)
                  </div>
                  <div className="flex flex-col gap-2">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".zip"
                      onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
                      className="w-full text-sm text-slate-600 file:mr-3 file:rounded-xl file:border-0 file:bg-[#5B5CFF] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white hover:file:bg-[#4a4bdd]"
                    />
                    <button
                      type="button"
                      disabled={!selectedFile || loadingUpload}
                      onClick={handleUpload}
                      className="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {loadingUpload ? "Uploading…" : "Upload Project"}
                    </button>
                  </div>

                  {uploadMessage && (
                    <div className={`mt-3 rounded-xl border px-3 py-2 text-xs ${
                      uploadStatus === "error"
                        ? "border-rose-200 bg-rose-50 text-rose-700"
                        : "border-emerald-200 bg-emerald-50 text-emerald-700"
                    }`}>
                      {uploadMessage}
                    </div>
                  )}
                </div>

                {/* Select from uploaded list */}
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                    Available uploaded projects
                  </div>
                  {sourcesQuery.isLoading ? (
                    <div className="text-xs text-slate-400">Loading…</div>
                  ) : uploadedProjects.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-400">
                      No uploaded projects yet. Upload a .zip above.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {uploadedProjects.map((p) => (
                        <button
                          key={p.name}
                          type="button"
                          onClick={() => {
                            setSourceProjectName(p.name)
                            setSourceProjectType("uploaded")
                          }}
                          className={`flex w-full items-center justify-between rounded-2xl border px-4 py-2.5 text-left text-sm transition-all ${
                            sourceProjectType === "uploaded" && sourceProjectName === p.name
                              ? "border-[#00AEEF] bg-[rgba(0,174,239,0.06)] font-medium text-slate-900"
                              : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                          }`}
                        >
                          <span>{p.name}</span>
                          {sourceProjectType === "uploaded" && sourceProjectName === p.name && (
                            <span className="text-xs text-[#00AEEF]">✓ selected</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Use Custom Project button */}
                <button
                  type="button"
                  disabled={!sourceProjectName}
                  onClick={() => setSourceProjectType("uploaded")}
                  className={`mt-auto ${
                    sourceProjectType === "uploaded" && sourceProjectName
                      ? "btn-secondary"
                      : "btn-primary disabled:cursor-not-allowed disabled:opacity-50"
                  }`}
                >
                  {sourceProjectType === "uploaded" && sourceProjectName
                    ? `Using: ${sourceProjectName}`
                    : "Use Custom Project"}
                </button>
              </div>
            </div>
          </div>

          {/* Validation warning for uploaded type */}
          {sourceProjectType === "uploaded" && !sourceProjectName && (
            <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              Please upload or select a custom project before starting the pipeline.
            </div>
          )}
        </SectionCard>

        {/* ── STEP 2 — Select User Story ──────────────────────────────────── */}
        <SectionCard className="p-6">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-[#00AEEF]">Step 2</div>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">Select User Story</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Pick the Jira story that will drive GraphRAG context injection, planning, generation, tests, and review.
          </p>

          {storiesQuery.isLoading ? (
            <div className="mt-5 text-sm text-slate-500">Loading Jira user stories...</div>
          ) : null}

          {storiesQuery.error ? (
            <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {storiesQuery.error.message || "Failed to load stories."}
            </div>
          ) : null}

          {!storiesQuery.isLoading && !storiesQuery.error ? (
            stories.length === 0 ? (
              <div className="mt-5 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
                No Jira stories returned. Configure Jira to populate this list.
              </div>
            ) : (
              <div className="mt-5 grid items-stretch gap-4 lg:grid-cols-2">
                {stories.map((story) => (
                  <CompactStoryCard
                    key={story.id}
                    story={story}
                    isSelected={selectedStory?.id === story.id}
                    onSelect={setSelectedStory}
                    graphLoaded={graphLoaded}
                  />
                ))}
              </div>
            )
          ) : null}
        </SectionCard>

        {/* ── STEP 3 — Run Pipeline ───────────────────────────────────────── */}
        <SectionCard className="p-6">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-[#10B981]">Step 3</div>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">Run AI-SDLC Pipeline</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Confirm the source project and the target Jira story, then launch the pipeline.
          </p>

          <div className="surface-muted mt-5 rounded-3xl p-5">
            <div className="text-sm font-medium text-slate-900">Launch summary</div>
            <div className="mt-4 space-y-3 text-sm text-slate-600">
              <div>
                <span className="font-medium text-slate-900">Source project:</span>{" "}
                {sourceLabel}
              </div>
              <div className="break-all">
                <span className="font-medium text-slate-900">Selected user story:</span>{" "}
                {selectedStory ? `${selectedStory.id} — ${selectedStory.title}` : "No user story selected"}
              </div>
              <div>
                <span className="font-medium text-slate-900">Generation output:</span>{" "}
                {selectedStory ? `output/generated/${selectedStory.id}` : "output/generated/<story-id>"}
              </div>
              <div>
                <span className="font-medium text-slate-900">source_project_type:</span>{" "}
                <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{sourceProjectType}</code>
              </div>
              {sourceProjectType === "uploaded" && sourceProjectName && (
                <div>
                  <span className="font-medium text-slate-900">source_project_name:</span>{" "}
                  <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{sourceProjectName}</code>
                </div>
              )}
            </div>
          </div>

          {/* Block warnings */}
          {sourceProjectType === "default" && selectedProject && !projectValidated ? (
            <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              Validate the selected base project before launching the pipeline.
            </div>
          ) : null}

          {sourceProjectType === "uploaded" && !sourceProjectName ? (
            <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              Please upload or select a custom project before starting the pipeline.
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleRun}
              disabled={!canRun}
              className="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
            >
              {createRunMutation.isPending ? "Launching pipeline..." : "Run pipeline on selected project"}
            </button>
            <div className="text-sm text-slate-500">Dry run is enabled for this demo launch.</div>
          </div>
        </SectionCard>

        {/* ── Pipeline Execution Flow ──────────────────────────────────────── */}
        <SectionCard className="p-6">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Pipeline Architecture</div>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">Pipeline Execution Flow</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Each run executes the following steps sequentially. Agents use LLMs (Qwen 2.5) to generate, test and review Java Spring Boot code.
          </p>

          <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {[
              { step: 1, icon: BookOpen,      label: "Story Loading",           desc: "Fetch & parse the Jira user story",        color: "text-indigo-600",  bg: "bg-indigo-50",  border: "border-indigo-200" },
              { step: 2, icon: Network,       label: "GraphRAG Injection",      desc: "Inject knowledge context into agents",     color: "text-violet-600",  bg: "bg-violet-50",  border: "border-violet-200" },
              { step: 3, icon: ListTodo,      label: "Planning",                desc: "Decompose story into ordered tasks",       color: "text-sky-600",     bg: "bg-sky-50",     border: "border-sky-200" },
              { step: 4, icon: Code2,         label: "Code Generation",         desc: "Generate Java entities, services, APIs",   color: "text-blue-600",    bg: "bg-blue-50",    border: "border-blue-200" },
              { step: 5, icon: Hammer,        label: "Compilation",             desc: "Run mvn compile, auto-fix errors",         color: "text-orange-600",  bg: "bg-orange-50",  border: "border-orange-200" },
              { step: 6, icon: TestTube2,     label: "Test Generation",         desc: "Generate JUnit unit tests",                color: "text-teal-600",    bg: "bg-teal-50",    border: "border-teal-200" },
              { step: 7, icon: Play,          label: "Test Execution",          desc: "Run mvn test + JaCoCo coverage",           color: "text-emerald-600", bg: "bg-emerald-50", border: "border-emerald-200" },
              { step: 8, icon: Star,          label: "Code Review",             desc: "LLM scores the generated code /100",       color: "text-yellow-600",  bg: "bg-yellow-50",  border: "border-yellow-200" },
              { step: 9, icon: ShieldCheck,   label: "Quality Gate",            desc: "Enforce coverage & review thresholds",     color: "text-rose-600",    bg: "bg-rose-50",    border: "border-rose-200" },
              { step: 10, icon: GitPullRequest, label: "GitHub Integration",    desc: "Commit, push branch & open pull request",  color: "text-slate-700",   bg: "bg-slate-100",  border: "border-slate-300" },
            ].map(({ step, icon: Icon, label, desc, color, bg, border }) => (
              <div key={step} className={`flex flex-col gap-2 rounded-2xl border ${border} ${bg} p-4`}>
                <div className="flex items-center justify-between">
                  <div className={`flex h-8 w-8 items-center justify-center rounded-lg bg-white border ${border}`}>
                    <Icon className={`h-4 w-4 ${color}`} />
                  </div>
                  <span className={`text-xs font-bold ${color} opacity-60`}>#{step}</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">{label}</p>
                  <p className="mt-0.5 text-xs leading-5 text-slate-500">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    </div>
  )
}
