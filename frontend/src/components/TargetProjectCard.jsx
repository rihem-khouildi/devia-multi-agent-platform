import { useMutation, useQuery } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import SectionCard from "./SectionCard"
import { api } from "../lib/api"

function badgeClasses(tone = "neutral") {
  if (tone === "success") return "border-emerald-200 bg-emerald-50 text-emerald-700"
  if (tone === "danger") return "border-rose-200 bg-rose-50 text-rose-700"
  if (tone === "accent") return "border-indigo-200 bg-indigo-50 text-indigo-700"
  return "border-slate-200 bg-slate-50 text-slate-600"
}

function statusTone(value) {
  const normalized = String(value || "").toUpperCase()
  if (["PASS", "AVAILABLE", "CONFIGURED", "READY", "VALIDATED"].includes(normalized)) return "success"
  if (["FAIL", "FAILED", "UNAVAILABLE", "MISSING"].includes(normalized)) return "danger"
  if (["SELECTED"].includes(normalized)) return "accent"
  return "neutral"
}

function StatusBadge({ label, value }) {
  return (
    <div className={`rounded-full border px-3 py-1 text-xs font-medium ${badgeClasses(statusTone(value))}`}>
      {label}: {value}
    </div>
  )
}

export default function TargetProjectCard({ selectedProject, onSelect, useButtonLabel }) {
  const [jobId, setJobId] = useState(null)
  const [validationResult, setValidationResult] = useState(null)
  const [validationError, setValidationError] = useState(null)

  const projectQuery = useQuery({
    queryKey: ["target-project"],
    queryFn: api.getTargetProject,
    staleTime: 30_000,
  })

  // Poll job status every 3s while jobId is set and not done
  const jobQuery = useQuery({
    queryKey: ["validation-job", jobId],
    queryFn: () => api.projects.getValidationJob(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.status === "done" || data?.status === "error") return false
      return 3000
    },
  })

  useEffect(() => {
    const data = jobQuery.data
    if (!data) return
    if (data.status === "done") {
      setValidationResult(data.result)
      setJobId(null)
      if (isSelected && project) onSelect({ ...project, validation: data.result })
    } else if (data.status === "error") {
      setValidationError(data.result?.error || "Validation failed.")
      setJobId(null)
    }
  }, [jobQuery.data])

  const startValidateMutation = useMutation({
    mutationFn: api.validateTargetProject,
    onSuccess: (data) => {
      setValidationError(null)
      setValidationResult(null)
      setJobId(data.job_id)
    },
    onError: (err) => {
      setValidationError(err.message || "Failed to start validation.")
    },
  })

  const project = projectQuery.data
  const validation = (selectedProject?.path === project?.path && selectedProject?.validation)
    ? selectedProject.validation
    : validationResult

  const isSelected = Boolean(selectedProject?.path && selectedProject?.path === project?.path)
  const isValidating = startValidateMutation.isPending || (jobId && jobQuery.data?.status === "running")

  function handleUseProject() {
    if (!project) return
    onSelect({ ...project, validation })
  }

  if (projectQuery.isLoading) {
    return <SectionCard className="p-6 text-sm text-slate-500">Loading target project...</SectionCard>
  }

  if (projectQuery.error) {
    return (
      <SectionCard className="border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
        {projectQuery.error.message || "Failed to load target project."}
      </SectionCard>
    )
  }

  return (
    <SectionCard className="overflow-hidden">
      <div className="border-b border-slate-200 px-6 py-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.24em] text-[#5B5CFF]">Base project</div>
            <h3 className="mt-2 text-2xl font-semibold text-slate-900">{project?.name}</h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">{project?.description}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge label="Status" value={validation?.overall_status || project?.status || "READY"} />
            {isSelected ? <StatusBadge label="Project" value="SELECTED" /> : null}
          </div>
        </div>
      </div>

      <div className="space-y-5 px-6 py-5">
        <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="surface-muted rounded-3xl p-4">
            <div className="text-sm font-medium text-slate-900">Project details</div>
            <div className="mt-3 space-y-2 text-sm text-slate-600">
              <div><span className="font-medium text-slate-900">Path:</span> {project?.path}</div>
              <div><span className="font-medium text-slate-900">Type:</span> {project?.type}</div>
              <div><span className="font-medium text-slate-900">Build tool:</span> {project?.build_tool}</div>
              <div><span className="font-medium text-slate-900">Java:</span> {project?.java}</div>
              <div><span className="font-medium text-slate-900">Spring Boot:</span> {project?.spring_boot}</div>
              <div><span className="font-medium text-slate-900">JaCoCo:</span> {project?.jacoco}</div>
            </div>
          </div>

          <div className="surface-muted rounded-3xl p-4">
            <div className="text-sm font-medium text-slate-900">Validation status</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <StatusBadge label="Compilation" value={validation?.compile?.status || "—"} />
              <StatusBadge label="JaCoCo" value={project?.jacoco || "—"} />
              {validation?.overall_status && (
                <StatusBadge label="Overall" value={validation.overall_status} />
              )}
            </div>
          </div>
        </div>

        {validationError ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {validationError}
          </div>
        ) : null}

        {validation?.compile?.errors?.length ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            <div className="mb-1 font-medium">Compilation errors</div>
            <ul className="list-inside list-disc space-y-0.5">
              {validation.compile.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        ) : null}

        {validation?.tests?.errors?.length ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            <div className="mb-1 font-medium">Test errors</div>
            <ul className="list-inside list-disc space-y-0.5">
              {validation.tests.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        ) : null}

        {isValidating && (
          <div className="rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-700">
            Validation en cours — compilation Maven sur le serveur. Veuillez patienter...
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={handleUseProject} className={isSelected ? "btn-secondary" : "btn-primary"}>
            {isSelected ? "Project selected" : (useButtonLabel || "Use this project")}
          </button>
          <button
            type="button"
            onClick={() => startValidateMutation.mutate()}
            disabled={isValidating}
            className="btn-secondary"
          >
            {isValidating ? "Validating…" : "Validate Project"}
          </button>
        </div>
      </div>
    </SectionCard>
  )
}
