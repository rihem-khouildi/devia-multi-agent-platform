const AGENTS = {
  analyst: {
    name: "Analyst Agent",
    avatar: "AN",
    accent: "bg-slate-900 text-white",
  },
  graphrag: {
    name: "GraphRAG Agent",
    avatar: "GR",
    accent: "bg-sky-100 text-sky-700",
  },
  planner: {
    name: "Planner Agent",
    avatar: "PL",
    accent: "bg-indigo-100 text-indigo-700",
  },
  developer: {
    name: "Developer Agent",
    avatar: "DE",
    accent: "bg-violet-100 text-violet-700",
  },
  compiler: {
    name: "Compiler",
    avatar: "CP",
    accent: "bg-amber-100 text-amber-700",
  },
  fixer: {
    name: "Fixer Agent",
    avatar: "FX",
    accent: "bg-rose-100 text-rose-700",
  },
  tester: {
    name: "Tester Agent",
    avatar: "TS",
    accent: "bg-emerald-100 text-emerald-700",
  },
  reviewer: {
    name: "Reviewer Agent",
    avatar: "RV",
    accent: "bg-cyan-100 text-cyan-700",
  },
  release: {
    name: "Release Agent",
    avatar: "RL",
    accent: "bg-fuchsia-100 text-fuchsia-700",
  },
}

function inferAgent(step) {
  switch (step) {
    case "story_loading":
      return AGENTS.analyst
    case "graphrag_context":
      return AGENTS.graphrag
    case "planning":
      return AGENTS.planner
    case "code_generation":
      return AGENTS.developer
    case "compile":
      return AGENTS.compiler
    case "fixer":
      return AGENTS.fixer
    case "test_generation":
    case "run_tests":
      return AGENTS.tester
    case "review":
    case "quality_gate":
      return AGENTS.reviewer
    case "human_approval":
    case "git_push":
      return AGENTS.release
    default:
      return AGENTS.analyst
  }
}

function stepTitle(step) {
  switch (step) {
    case "story_loading":
      return "story intake"
    case "graphrag_context":
      return "GraphRAG context"
    case "planning":
      return "planning"
    case "code_generation":
      return "implementation"
    case "compile":
      return "compilation"
    case "fixer":
      return "repair"
    case "test_generation":
      return "test generation"
    case "run_tests":
      return "test execution"
    case "review":
      return "review"
    case "quality_gate":
      return "quality gate"
    case "human_approval":
      return "human approval"
    case "git_push":
      return "release"
    default:
      return step.replaceAll("_", " ")
  }
}

function buildMessage(event) {
  const step = event.step
  const status = String(event.status || "").toLowerCase()
  const details = event.details || {}

  if (step === "planning" && status === "running") {
    return "Planner Agent is decomposing the user story."
  }

  if (step === "compile" && status === "failed") {
    return "Compiler detected errors. Fixer Agent will repair them."
  }

  if (step === "story_loading") {
    if (status === "running") return "Analyst Agent is loading and validating the user story."
    if (status === "success") return "Analyst Agent accepted the user story and shared it with the pipeline."
  }

  if (step === "graphrag_context") {
    if (status === "running") return "GraphRAG Agent is checking whether architecture context is available."
    if (status === "success") return "GraphRAG Agent injected contextual knowledge into the run."
    if (status === "skipped") return "GraphRAG Agent found no loaded context and let the pipeline continue."
  }

  if (step === "planning") {
    if (status === "success") return "Planner Agent finished the execution plan for the story."
    if (status === "failed") return "Planner Agent could not complete the story decomposition."
  }

  if (step === "code_generation") {
    if (status === "running") return "Developer Agent is generating the implementation files."
    if (status === "success") return "Developer Agent completed the first implementation pass."
    if (status === "failed") return "Developer Agent hit a generation issue during implementation."
  }

  if (step === "compile") {
    if (status === "running") return "Compiler is validating that the generated code builds cleanly."
    if (status === "success") return "Compiler validated the codebase successfully."
  }

  if (step === "fixer") {
    if (status === "running") return "Fixer Agent is applying targeted repairs to unblock compilation."
    if (status === "success") return "Fixer Agent finished its repair cycle."
    if (status === "failed") return "Fixer Agent could not fully repair the detected issues."
  }

  if (step === "test_generation") {
    if (status === "running") return "Tester Agent is generating automated tests."
    if (status === "success") return "Tester Agent produced the test suite."
    if (status === "failed") return "Tester Agent failed while preparing the test suite."
  }

  if (step === "run_tests") {
    if (status === "running") return "Tester Agent is running the generated tests."
    if (status === "success") return "Tester Agent completed test execution successfully."
    if (status === "failed") return "Tester Agent found failing tests in the current build."
  }

  if (step === "review") {
    if (status === "running") return "Reviewer Agent is evaluating the implementation quality."
    if (status === "success") return details.review_score != null
      ? `Reviewer Agent approved the implementation with a score of ${details.review_score}.`
      : "Reviewer Agent completed its review."
    if (status === "failed") return "Reviewer Agent raised issues that must be addressed."
  }

  if (step === "quality_gate") {
    if (status === "running") return "Reviewer Agent is evaluating the final quality gate."
    if (status === "success") return "Reviewer Agent confirmed that the quality gate passed."
    if (status === "failed") return "Reviewer Agent rejected the run at the quality gate."
  }

  if (step === "human_approval") {
    if (status === "running") return "Release Agent is waiting for human approval on generated files."
    if (status === "success") return "Release Agent received all required human approvals."
    if (status === "failed") return "Release Agent is blocked by rejected files."
  }

  if (step === "git_push") {
    if (status === "running") return "Release Agent is pushing the approved result to GitHub."
    if (status === "success") return details.commit_sha
      ? `Release Agent completed the GitHub push with commit ${details.commit_sha}.`
      : "Release Agent completed the GitHub push."
    if (status === "failed") return "Release Agent could not finish the GitHub push."
    if (status === "skipped") return "Release Agent is waiting for file review approval before pushing to GitHub."
  }

  return event.message || `${inferAgent(step).name} reported an update on ${stepTitle(step)}.`
}

export function mapEventsToAgentMessages(events = []) {
  return events.map((event) => {
    const agent = inferAgent(event.step)
    return {
      id: event.id,
      step: event.step,
      status: event.status,
      created_at: event.created_at,
      agent,
      message: buildMessage(event),
      rawMessage: event.message,
      details: event.details || {},
    }
  })
}

export { AGENTS }
