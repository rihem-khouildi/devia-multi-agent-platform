export const JURY_PIPELINE_STEPS = [
  { key: "story_loading", label: "Story Loading" },
  { key: "graphrag_context", label: "GraphRAG" },
  { key: "planning", label: "Planning" },
  { key: "code_generation", label: "Code Generation" },
  { key: "compile", label: "Compile" },
  { key: "fixer", label: "Fixer" },
  { key: "test_generation", label: "Test Generation" },
  { key: "run_tests", label: "Tests" },
  { key: "review", label: "Review" },
  { key: "quality_gate", label: "Quality Gate" },
  { key: "human_approval", label: "Human Approval" },
  { key: "git_push", label: "GitHub Push" },
]

const SUMMARY_STEP_MAP = {
  resolve_user_story: "story_loading",
  advisor: "planning",
  planner: "planning",
  developer: "code_generation",
  compile: "compile",
  fixer: "fixer",
  tester: "test_generation",
  run_tests: "run_tests",
  reviewer: "review",
  quality_gate: "quality_gate",
  commit: "git_push",
}

export function normalizePipelineStatus(status) {
  const value = String(status || "").toLowerCase()
  if (value === "completed" || value === "success") return "success"
  if (value === "running") return "running"
  if (value === "failed" || value === "error") return "failed"
  if (value === "skipped") return "skipped"
  return "pending"
}

function buildEventMap(events = []) {
  const map = {}
  for (const event of events) {
    map[event.step] = event
  }
  return map
}

function buildSummaryMap(summary) {
  const map = {}
  for (const step of summary?.steps || []) {
    const canonical = SUMMARY_STEP_MAP[step.name]
    if (canonical && !map[canonical]) {
      map[canonical] = step
    }
  }
  return map
}

function deriveHumanApproval(summary, files, eventsByStep) {
  if (!summary) {
    return { status: "pending", message: "Waiting for run data." }
  }

  // Gate: Human Approval is only active once Quality Gate has succeeded.
  const qualityGateEvent = eventsByStep && eventsByStep["quality_gate"]
  const qualityGateStatus = qualityGateEvent
    ? normalizePipelineStatus(qualityGateEvent.status)
    : (summary.all_gates_passed === true ? "success" : "pending")

  if (qualityGateStatus === "failed") {
    return {
      status: "pending",
      message: "Human approval unavailable — Quality Gate failed.",
    }
  }

  if (qualityGateStatus !== "success") {
    return {
      status: "pending",
      message: "Waiting for Quality Gate success before human approval.",
    }
  }

  // Quality Gate passed — proceed with normal approval logic.
  if (!files || (files.total === 0 && summary.files_generated > 0)) {
    return { status: "running", message: "Generated files will appear here for reviewer approval." }
  }

  if (!files || files.total === 0) {
    return { status: "pending", message: "No generated files available yet." }
  }

  if (files.all_approved) {
    return {
      status: "success",
      message: `Approved ${files.accepted}/${files.total} generated file(s).`,
      details: { accepted: files.accepted, total: files.total },
    }
  }

  if (files.rejected > 0) {
    return {
      status: "failed",
      message: `${files.rejected} file(s) rejected. Approval is blocking release.`,
      details: { pending: files.pending, rejected: files.rejected },
    }
  }

  return {
    status: "running",
    message: `${files.pending} file(s) waiting for human approval.`,
    details: { pending: files.pending, accepted: files.accepted, total: files.total },
  }
}

function deriveGitPush(summary, eventsByStep, files) {
  const event = eventsByStep.git_push

  if (summary?.commit_sha) {
    return {
      status: "success",
      message: "GitHub push completed successfully.",
      details: { commit_sha: summary.commit_sha },
      created_at: event?.created_at,
    }
  }

  if (event) {
    if (event.status === "skipped" && !files?.all_approved) {
      return {
        status: "pending",
        message: "Waiting for human approval before GitHub push.",
        details: event.details,
        created_at: event.created_at,
      }
    }

    return {
      status: normalizePipelineStatus(event.status),
      message: event.message,
      details: event.details,
      created_at: event.created_at,
    }
  }

  if (files?.all_approved && summary?.status !== "running") {
    return { status: "pending", message: "Ready to trigger GitHub push." }
  }

  return { status: "pending", message: "GitHub push will become available after approval." }
}

export function buildPipelineStepStates({ summary, events = [], files }) {
  const eventsByStep = buildEventMap(events)
  const summaryByStep = buildSummaryMap(summary)

  return JURY_PIPELINE_STEPS.map((step) => {
    if (step.key === "human_approval") {
      return { ...step, ...deriveHumanApproval(summary, files, eventsByStep) }
    }

    if (step.key === "git_push") {
      return { ...step, ...deriveGitPush(summary, eventsByStep, files) }
    }

    const event = eventsByStep[step.key]
    const summaryStep = summaryByStep[step.key]

    if (event) {
      return {
        ...step,
        status: normalizePipelineStatus(event.status),
        message: event.message,
        details: event.details,
        created_at: event.created_at,
      }
    }

    if (summaryStep) {
      return {
        ...step,
        status: normalizePipelineStatus(summaryStep.status),
        message: summaryStep.error || null,
        details: summaryStep.duration_seconds != null ? { duration_seconds: summaryStep.duration_seconds } : undefined,
      }
    }

    if (step.key === "review" && summary?.review_score != null) {
      return {
        ...step,
        status: "success",
        message: `Review score recorded: ${summary.review_score}/100.`,
        details: { review_score: summary.review_score },
      }
    }

    return { ...step, status: "pending", message: null }
  })
}

export function calculatePipelineProgress(stepStates = []) {
  if (!stepStates.length) return 0

  const units = stepStates.reduce((total, step) => {
    if (["success", "failed", "skipped"].includes(step.status)) return total + 1
    if (step.status === "running") return total + 0.5
    return total
  }, 0)

  return Math.max(0, Math.min(100, Math.round((units / stepStates.length) * 100)))
}

export function findActiveStep(stepStates = []) {
  return stepStates.find((step) => step.status === "running")
    || stepStates.find((step) => step.status === "failed")
    || stepStates.find((step) => step.status === "pending")
    || stepStates.at(-1)
}
