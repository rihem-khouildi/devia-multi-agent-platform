export const AUTO_COVERAGE_RETRY_ENABLED = false

const timeline = [
  { step: 1, stage: "Story Loading", duration: "00:02", description: "Loaded user story TEST-1 from Jira", status: "success" },
  { step: 2, stage: "GraphRAG Injection", duration: "00:04", description: "Injected domain context via GraphRAG", status: "success" },
  { step: 3, stage: "Repository Analysis", duration: "00:06", description: "Analyzed codebase & dependencies", status: "success" },
  { step: 4, stage: "Planning", duration: "00:08", description: "Generated execution plan & tasks", status: "success" },
  { step: 5, stage: "Code Generation", duration: "00:18", description: "Generated Spring Boot code artifacts", status: "success" },
  { step: 6, stage: "Maven Compile", duration: "00:21", description: "Compiled source with Maven", status: "success" },
  { step: 7, stage: "Test Generation", duration: "00:12", description: "Generated unit & integration tests", status: "success" },
  { step: 8, stage: "Test Execution", duration: "00:15", description: "Executed tests via Maven Surefire", status: "success" },
  { step: 9, stage: "Coverage Analysis", duration: "00:06", description: "JaCoCo detected insufficient test coverage", status: "warning" },
  { step: 10, stage: "Review", duration: "00:07", description: "Code & test review by Reviewer agent", status: "success" },
  { step: 11, stage: "Quality Gate", duration: "00:02", description: "Coverage below required threshold", status: "failed" },
  { step: 12, stage: "GitHub Push", duration: "00:01", description: "Push blocked until quality gate passes", status: "blocked" },
]

const baseRun = {
  run_id: "RUN-2026-051",
  story_id: "TEST-1",
  route: "coverage_below_threshold",
  next_action: "manual_test_improvement_required",
  coverage: "42.8%",
  required: "70%",
  compile_status: "passed",
  test_status: "passed",
  github_push: "blocked",
}

const graphRagContext = {
  domain: "Authentication",
  bounded_context: "Auth Service",
  patterns: [
    "Spring Security",
    "DTO Validation",
    "Repository Pattern",
  ],
  related_entities: [
    "AuthController",
    "AuthService",
    "UserRepository",
    "LoginRequestDTO",
  ],
  business_rules: [
    "Users must authenticate before access",
    "Invalid login attempts are rate limited",
  ],
}

const agentActivity = [
  {
    name: "Planner Agent",
    status: "Completed",
    time: "00:08",
    input: "User story, context",
    outcomeLabel: "Decision/output",
    outcome: "Plan with 12 tasks",
  },
  {
    name: "Developer Agent",
    status: "Completed",
    time: "00:18",
    input: "Plan, context",
    outcomeLabel: "Output",
    outcome: "5 source files",
  },
  {
    name: "Tester Agent",
    status: "Completed",
    time: "00:27",
    input: "Source code",
    outcomeLabel: "Output",
    outcome: "18 tests, all passed",
  },
  {
    name: "Reviewer Agent",
    status: "Completed",
    time: "00:07",
    input: "Code, tests, coverage",
    outcomeLabel: "Decision",
    outcome: "Coverage below threshold",
  },
]

const generatedFiles = [
  { file: "AuthController.java", type: "Source", status: "Accepted" },
  { file: "AuthService.java", type: "Source", status: "Accepted" },
  { file: "LoginRequest.java", type: "Source", status: "Accepted" },
  { file: "AuthServiceTest.java", type: "Test", status: "Needs Improvement" },
]

const diagnostics = {
  failedStage: "Quality Gate",
  category: "coverage_below_threshold",
  message: "Tests passed, but coverage is below required threshold.",
  suggestedAction: "Improve or regenerate tests before merge.",
}

const agentChain = [
  {
    key: "jira",
    name: "Jira Loader",
    role: "Pulls the user story",
    artifact: "TEST-1 spec",
    status: "success",
    icon: "stories",
  },
  {
    key: "graphrag",
    name: "GraphRAG Retriever",
    role: "Injects project memory",
    artifact: "Auth context bundle",
    status: "success",
    icon: "graph",
  },
  {
    key: "analyzer",
    name: "Analyzer",
    role: "Maps impacted modules",
    artifact: "5 impacted files",
    status: "success",
    icon: "file",
  },
  {
    key: "planner",
    name: "Planner",
    role: "Designs the change plan",
    artifact: "12-task plan",
    status: "success",
    icon: "run",
  },
  {
    key: "developer",
    name: "Developer",
    role: "Generates Spring Boot code",
    artifact: "5 source files",
    status: "success",
    icon: "launch",
  },
  {
    key: "tester",
    name: "Tester",
    role: "Generates & runs tests",
    artifact: "18 tests passed",
    status: "success",
    icon: "success",
  },
  {
    key: "reviewer",
    name: "Reviewer",
    role: "Audits code & coverage",
    artifact: "Coverage 42.8%",
    status: "warning",
    icon: "warning",
  },
  {
    key: "quality",
    name: "Quality Gate",
    role: "Protects the repository",
    artifact: "Push blocked",
    status: "blocked",
    icon: "shield",
  },
]

const coverageRemediation = {
  detectedIssue: "Coverage below required threshold",
  whyItMatters:
    "Tests passed, but they do not cover enough business logic to safely push the generated code.",
  rootCause:
    "The generated test suite validates basic behavior, but it probably misses edge cases and negative scenarios.",
  safetyRule: "GitHub push remains blocked until coverage reaches the required threshold.",
  suggestedNextAction: "Manual test improvement required",
  missingAreas: [
    {
      key: "invalid_input",
      title: "Invalid input validation",
      detail: "@Valid violations on LoginRequest are never asserted by current tests.",
      icon: "warning",
    },
    {
      key: "empty_or_null",
      title: "Empty or null fields",
      detail: "Empty username and missing password paths are not exercised.",
      icon: "warning",
    },
    {
      key: "failed_auth",
      title: "Failed authentication path",
      detail: "Wrong credentials and locked accounts have no negative tests.",
      icon: "failed",
    },
    {
      key: "service_exception",
      title: "Service exception path",
      detail: "AuthService throws AuthenticationFailedException / RateLimitedException without coverage.",
      icon: "failed",
    },
    {
      key: "repository_failure",
      title: "Repository failure behavior",
      detail: "UserRepository timeout / DataAccessException branch is unreachable from the suite.",
      icon: "blocked",
    },
    {
      key: "controller_bad_request",
      title: "Controller bad request responses",
      detail: "400 responses for malformed payloads are not verified via MockMvc.",
      icon: "warning",
    },
  ],
  improvementPlan: [
    {
      key: "plan_invalid_credentials",
      step: "Add tests for invalid credentials",
      target: "AuthServiceTest.java",
      hint: "Wrong password should raise AuthenticationFailedException with code AUTH-401.",
    },
    {
      key: "plan_missing_fields",
      step: "Add tests for missing username/password",
      target: "AuthControllerTest.java",
      hint: "POST /auth/login with empty body should produce 400 and surface bean-validation messages.",
    },
    {
      key: "plan_repository_exception",
      step: "Add tests for repository exception",
      target: "AuthControllerIT.java",
      hint: "Inject a UserRepository stub that throws DataAccessException; assert the controller maps it to 500.",
    },
    {
      key: "plan_service_error",
      step: "Add tests for service error handling",
      target: "AuthServiceTest.java",
      hint: "Cover RateLimitedException after five failed attempts and AccountLockedException for locked users.",
    },
    {
      key: "plan_controller_bad_request",
      step: "Add tests for controller bad request response",
      target: "AuthControllerTest.java",
      hint: "Send malformed JSON; verify 400, error code BAD_REQUEST, and field-level violation list.",
    },
  ],
}

const securityCheck = {
  status: "passed",
  scannedAt: "2026-05-08T09:42:11Z",
  scope: "Generated source + project configuration",
  description:
    "Security sanity checks help prevent obvious risks such as hardcoded credentials, sensitive logs, missing input validation, or unsafe configuration.",
  futureWork:
    "Advanced security scanning such as SAST or dependency vulnerability analysis can be integrated in a future version.",
  criteria: [
    {
      key: "no_hardcoded_secrets",
      label: "No hardcoded secrets detected",
      detail: "Scanned generated files for API keys, JWT secrets, and DB credentials — no matches.",
      status: "passed",
      icon: "lock",
    },
    {
      key: "no_sensitive_logging",
      label: "No sensitive logging detected",
      detail: "No log statements emit raw passwords, tokens, or PII fields.",
      status: "passed",
      icon: "shield",
    },
    {
      key: "input_validation",
      label: "Input validation detected",
      detail: "LoginRequest uses @Valid + @NotBlank; controller binds @Validated.",
      status: "passed",
      icon: "success",
    },
    {
      key: "safe_configuration",
      label: "No dangerous configuration detected",
      detail: "Spring Security CSRF stays enabled; CORS is restricted to known origins; debug endpoints are off.",
      status: "passed",
      icon: "shield",
    },
  ],
}

const qualityCriteria = [
  {
    key: "compile",
    label: "Compilation passed",
    detail: "Maven built the generated Spring Boot artifacts without errors.",
    status: "passed",
    icon: "success",
  },
  {
    key: "tests",
    label: "Tests passed",
    detail: "18 unit + MockMvc tests executed via Surefire — 0 failures.",
    status: "passed",
    icon: "success",
  },
  {
    key: "tests_discovered",
    label: "Tests discovered",
    detail: "Tester agent emitted a non-empty test plan (18 cases discovered).",
    status: "passed",
    icon: "success",
  },
  {
    key: "coverage",
    label: "Coverage check failed",
    detail: "JaCoCo reported 42.8% line coverage — below the required 70%.",
    status: "failed",
    icon: "warning",
  },
  {
    key: "reports_readable",
    label: "Reports readable",
    detail: "Surefire and JaCoCo reports parsed successfully.",
    status: "passed",
    icon: "success",
  },
  {
    key: "reviewer",
    label: "Reviewer check passed",
    detail: "Static review found no critical issues; code style approved.",
    status: "passed",
    icon: "success",
  },
  {
    key: "security",
    label: "Security sanity check passed",
    detail: "No hardcoded secrets, sensitive logs, missing validation, or unsafe configuration.",
    status: "passed",
    icon: "shield",
  },
  {
    key: "human_validation",
    label: "Human validation incomplete or pending",
    detail: "Manual review of generated files has not been signed off.",
    status: "pending",
    icon: "pending",
  },
]

const agentLogs = [
  {
    agent: "Planner Agent",
    icon: "run",
    tone: "indigo",
    lines: [
      "[00:00.12] Loaded user story TEST-1 from Jira",
      "[00:00.85] Retrieved GraphRAG context bundle (5 impacted files)",
      "[00:01.40] Generated 12-task plan across 4 phases",
      "[00:02.05] Plan validated against scope: PASS",
      "[00:02.21] Wrote plan.json (4.1 KB)",
    ],
  },
  {
    agent: "Developer Agent",
    icon: "launch",
    tone: "violet",
    lines: [
      "[00:02.30] Started code generation",
      "[00:04.18] Generated AuthController.java",
      "[00:06.55] Updated AuthService.java with rate-limit guard",
      "[00:09.12] Generated LoginRequest.java DTO",
      "[00:18.04] Wrote diff_developer.patch (+312 / -48 LOC)",
    ],
  },
  {
    agent: "Tester Agent",
    icon: "success",
    tone: "emerald",
    lines: [
      "[00:18.20] Loaded test profile from existing project",
      "[00:21.41] Generated 18 unit + MockMvc tests",
      "[00:24.07] mvn test invoked (Surefire)",
      "[00:26.48] Result: 18 tests, 0 failures",
      "[00:27.10] Wrote surefire-reports/",
    ],
  },
  {
    agent: "Reviewer Agent",
    icon: "warning",
    tone: "amber",
    lines: [
      "[00:27.30] Static review: 0 critical findings",
      "[00:30.22] JaCoCo coverage report ingested",
      "[00:30.84] Line coverage 42.8% / branch 31.2%",
      "[00:31.05] Verdict: COVERAGE_BELOW_THRESHOLD",
      "[00:31.18] Wrote review_report.md",
    ],
  },
]

const agentArtifacts = [
  {
    key: "analyzer",
    agent: "Analyzer",
    role: "Reads the repository",
    icon: "graph",
    tone: "sky",
    artifactName: "Repository analysis",
    artifactType: "Markdown report",
    artifactFile: "repo_analysis.md",
    summary: "Map of impacted modules, dependency graph, and architectural fingerprint of the Spring Boot codebase.",
    metrics: ["5 impacted files", "0 schema changes", "12 dependencies inspected"],
    consumedBy: "Planner",
  },
  {
    key: "planner",
    agent: "Planner",
    role: "Designs the change plan",
    icon: "run",
    tone: "indigo",
    artifactName: "Implementation plan",
    artifactType: "JSON task graph",
    artifactFile: "plan.json",
    summary: "12 sequenced tasks across 4 phases — scaffolding, code edits, test scaffolding, validation.",
    metrics: ["12 tasks", "4 phases", "Critical path 1m40s"],
    consumedBy: "Developer",
  },
  {
    key: "developer",
    agent: "Developer",
    role: "Generates source code",
    icon: "launch",
    tone: "violet",
    artifactName: "Source code files",
    artifactType: "Java patch",
    artifactFile: "diff_developer.patch",
    summary: "Spring Boot artifacts following the project's existing DTO Validation and Repository patterns.",
    metrics: ["5 source files", "+312 / -48 LOC", "0 new dependencies"],
    consumedBy: "Tester",
  },
  {
    key: "tester",
    agent: "Tester",
    role: "Writes & runs tests",
    icon: "success",
    tone: "emerald",
    artifactName: "JUnit test suite",
    artifactType: "Surefire reports",
    artifactFile: "surefire-reports/",
    summary: "Unit and MockMvc tests targeting controller and service surfaces, executed via Maven Surefire.",
    metrics: ["18 tests", "0 failures", "Run time 0:15"],
    consumedBy: "Reviewer",
  },
  {
    key: "reviewer",
    agent: "Reviewer",
    role: "Audits quality & coverage",
    icon: "warning",
    tone: "amber",
    artifactName: "Review notes",
    artifactType: "Markdown report + JaCoCo",
    artifactFile: "review_report.md",
    summary: "Code style approved; coverage flagged below threshold with a per-class breakdown and suggested gaps.",
    metrics: ["Coverage 42.8%", "Branch 31.2%", "0 critical findings"],
    consumedBy: "Quality Gate",
  },
  {
    key: "quality_gate",
    agent: "Quality Gate",
    role: "Decides what ships",
    icon: "shield",
    tone: "rose",
    artifactName: "Final validation decision",
    artifactType: "Decision JSON",
    artifactFile: "quality_gate_decision.json",
    summary: "Authoritative ship/block verdict, the only artifact allowed to trigger a GitHub push.",
    metrics: ["Verdict: BLOCKED", "route = coverage_below_threshold", "github_push = blocked"],
    consumedBy: "GitHub",
  },
]

const coverageGap = {
  current: 42.8,
  required: 70,
  gap: 27.2,
  measuredBy: "JaCoCo",
  scope: "AuthService.java + AuthController.java",
  branchCoverage: 31.2,
  branchRequired: 60,
  missingAreas: [
    {
      key: "input_validation",
      title: "Invalid input validation",
      detail: "@Valid rejections on LoginRequest are never executed by current tests.",
      impact: "high",
      estimatedUplift: 8.4,
      icon: "warning",
      target: "LoginRequest.java",
    },
    {
      key: "service_errors",
      title: "Service error paths",
      detail: "AuthService throws AuthenticationFailedException and RateLimitedException — neither is asserted.",
      impact: "high",
      estimatedUplift: 9.6,
      icon: "failed",
      target: "AuthService.java",
    },
    {
      key: "repository_failure",
      title: "Repository failure behavior",
      detail: "UserRepository timeout / DataAccessException branch is unreachable from the current test suite.",
      impact: "medium",
      estimatedUplift: 5.1,
      icon: "blocked",
      target: "UserRepository.java",
    },
    {
      key: "edge_cases",
      title: "Edge cases",
      detail: "Empty username, locked accounts and case-insensitive matching are not exercised.",
      impact: "medium",
      estimatedUplift: 4.6,
      icon: "target",
      target: "AuthServiceTest.java",
    },
  ],
  recommendedTests: [
    {
      key: "rec_invalid_payload",
      name: "shouldRejectLoginWhenPayloadIsInvalid",
      target: "AuthControllerTest.java",
      type: "MockMvc",
      detail: "POST /auth/login with empty username should respond 400 and surface a 'username must not be blank' violation.",
      gain: 6.0,
    },
    {
      key: "rec_locked_account",
      name: "shouldReturn423WhenAccountIsLocked",
      target: "AuthServiceTest.java",
      type: "Unit",
      detail: "Mock a locked user and assert AuthService raises AccountLockedException with the right error code.",
      gain: 5.4,
    },
    {
      key: "rec_rate_limit",
      name: "shouldRateLimitAfterFiveFailedAttempts",
      target: "AuthServiceTest.java",
      type: "Unit",
      detail: "Drive 5 failed logins in a row and assert the 6th call throws RateLimitedException.",
      gain: 4.8,
    },
    {
      key: "rec_repo_failure",
      name: "shouldPropagateRepositoryFailureAs500",
      target: "AuthControllerIT.java",
      type: "Integration",
      detail: "Inject a UserRepository stub that throws DataAccessException and assert the controller maps it to 500.",
      gain: 4.5,
    },
    {
      key: "rec_case_insensitive",
      name: "shouldMatchUsernameCaseInsensitively",
      target: "AuthServiceTest.java",
      type: "Unit",
      detail: "Authenticate 'Alice' against a stored 'alice' and confirm the lookup is case-insensitive.",
      gain: 2.5,
    },
  ],
}

const decisionJournal = [
  {
    key: "jira",
    agent: "Jira Loader",
    icon: "stories",
    tone: "sky",
    decision: "Story TEST-1 accepted as input",
    reason: "Story is in 'Ready for Dev' with non-empty acceptance criteria and a known epic.",
    evidence: [
      "Jira status = Ready for Dev",
      "8 acceptance criteria parsed",
      "Epic AUTH-EPIC-12 linked",
    ],
    risk: "Low — story scope is bounded to the Authentication context.",
    artifact: "story_payload.json",
    confidence: 0.96,
  },
  {
    key: "graphrag",
    agent: "GraphRAG Retriever",
    icon: "brain",
    tone: "violet",
    decision: "Injected the Auth bounded-context memory bundle",
    reason: "Vector + symbol search converged on the same 5 files, indicating high relevance for the change.",
    evidence: [
      "Top-k similarity ≥ 0.82 for AuthService and LoginRequest",
      "5 impacted files cross-validated by symbol graph",
      "Confidence reported as High",
    ],
    risk: "Medium — UserRepository has a sibling write path not exercised by the story.",
    artifact: "graphrag_context.json",
    confidence: 0.91,
  },
  {
    key: "analyzer",
    agent: "Repository Analyzer",
    icon: "graph",
    tone: "sky",
    decision: "Mapped impact to 5 files, no schema migration required",
    reason: "Targeted classes already exist; the change is additive on the controller and service layer.",
    evidence: [
      "AuthController, AuthService, UserRepository present",
      "No JPA entity rename detected",
      "pom.xml dependencies already cover Spring Security",
    ],
    risk: "Low — additive change, no breaking import detected.",
    artifact: "repo_analysis.md",
    confidence: 0.94,
  },
  {
    key: "planner",
    agent: "Planner",
    icon: "run",
    tone: "indigo",
    decision: "Generated a 12-task plan biased toward test coverage",
    reason: "Story carries 8 acceptance criteria, so the plan front-loads test scaffolding before code edits.",
    evidence: [
      "12 tasks across 4 phases",
      "5 of 12 tasks dedicated to tests",
      "Critical path estimated at 1m40s",
    ],
    risk: "Low — plan stays within GraphRAG-declared scope.",
    artifact: "plan.json",
    confidence: 0.89,
  },
  {
    key: "developer",
    agent: "Developer",
    icon: "launch",
    tone: "indigo",
    decision: "Generated 5 source files using Spring Security idioms",
    reason: "Patterns retrieved by GraphRAG (DTO Validation, Repository Pattern) matched the project's existing style.",
    evidence: [
      "AuthController.java created",
      "AuthService.java updated with rate-limit guard",
      "LoginRequest DTO added with @Valid",
    ],
    risk: "Medium — rate-limit guard is new behavior not directly covered by AC1–AC8.",
    artifact: "diff_developer.patch",
    confidence: 0.87,
  },
  {
    key: "tester",
    agent: "Tester",
    icon: "success",
    tone: "emerald",
    decision: "Generated 18 tests, all green on first run",
    reason: "Tests target the controller and service surface; integration tests use the existing test profile.",
    evidence: [
      "18 tests / 0 failures via Surefire",
      "Happy-path + 4 error-path tests",
      "MockMvc + @SpringBootTest used as in the codebase",
    ],
    risk: "High — error-path branches are present in code but not exercised by tests, leaving coverage at 42.8%.",
    artifact: "surefire-reports/",
    confidence: 0.78,
  },
  {
    key: "reviewer",
    agent: "Reviewer",
    icon: "warning",
    tone: "amber",
    decision: "Flagged coverage as below threshold, code style approved",
    reason: "JaCoCo line coverage 42.8% is below the configured 70% gate; static review found no critical issues.",
    evidence: [
      "JaCoCo: 42.8% line / 31.2% branch",
      "0 critical SonarQube-equivalent findings",
      "AuthServiceTest.java covers only the happy path",
    ],
    risk: "High — merging now would lower repository-wide coverage.",
    artifact: "review_report.md",
    confidence: 0.92,
  },
  {
    key: "quality",
    agent: "Quality Gate",
    icon: "shield",
    tone: "rose",
    decision: "Blocked the GitHub push — repository protected",
    reason: "AUTO_COVERAGE_RETRY_ENABLED is false and coverage gap is 27.2 points; policy mandates manual intervention.",
    evidence: [
      "route = coverage_below_threshold",
      "next_action = manual_test_improvement_required",
      "auto_coverage_retry = disabled",
    ],
    risk: "None — protective decision; no code shipped.",
    artifact: "quality_gate_decision.json",
    confidence: 0.99,
  },
]

const nextActions = [
  {
    title: "Improve AuthServiceTest.java",
    detail: "Add tests for the rate-limited login path and invalid credential branch to lift coverage above 70%.",
    cta: "Open file in editor",
    tone: "primary",
  },
  {
    title: "Review JaCoCo coverage report",
    detail: "Inspect uncovered branches reported by JaCoCo and target the highest-impact gaps first.",
    cta: "View coverage report",
    tone: "secondary",
  },
  {
    title: "Re-run validation before merge",
    detail: "Once tests are improved, replay the run to clear the quality gate and unblock the GitHub push.",
    cta: "Replay run",
    tone: "secondary",
  },
]

const microcopy = {
  blocked: "Blocked to protect repository quality",
  coverageHeadline: "JaCoCo detected insufficient test coverage",
  pushBlocked: "Push blocked until quality gate passes",
  nextActionFriendly: "Manual test improvement required",
}

function buildSummaryCards(qualityGateStatus) {
  return [
    { title: "User Stories", value: "24", badge: "From Jira", status: "info", icon: "stories" },
    { title: "GraphRAG Status", value: "Injected", badge: "Context Ready", status: "success", icon: "graph" },
    { title: "Last Run", value: "Validation Blocked", badge: "RUN-2026-051", status: "warning", icon: "run" },
    {
      title: "Quality Gate",
      value: qualityGateStatus === "blocked" ? "Blocked" : "Passed",
      badge: qualityGateStatus === "blocked" ? "Manual Action Required" : "Ready to Merge",
      status: qualityGateStatus === "blocked" ? "failed" : "success",
      icon: "shield",
    },
  ]
}

function buildNarrative(runSummary) {
  return [
    { highlight: "Story", text: `Devia loaded the Jira user story ${runSummary.story_id}.` },
    { highlight: "Context", text: "GraphRAG injected the Authentication bounded context as project memory." },
    { highlight: "Code", text: "Spring Boot artifacts were generated and compiled successfully via Maven." },
    { highlight: "Tests", text: "Tester agent generated and executed 18 tests — all passed." },
    { highlight: "Coverage", text: `JaCoCo measured ${runSummary.coverage} coverage, below the required ${runSummary.required}.` },
    { highlight: "Decision", text: "The Quality Gate blocked the GitHub push to protect the repository from incomplete validation." },
  ]
}

export function getMissionControlData(overrides = {}) {
  const runSummary = { ...baseRun, ...(overrides.runSummary || {}) }
  const coverageBlocked = runSummary.route === "coverage_below_threshold" && AUTO_COVERAGE_RETRY_ENABLED === false

  const qualityGateStatus = coverageBlocked ? "blocked" : "success"
  const githubPushStatus = coverageBlocked ? "blocked" : runSummary.github_push
  const nextAction = coverageBlocked ? "manual_test_improvement_required" : runSummary.next_action
  const lastRunState = coverageBlocked ? "Validation Blocked" : "Successful"

  const enrichedRun = {
    ...runSummary,
    next_action: nextAction,
    github_push: githubPushStatus,
    quality_gate: qualityGateStatus,
    last_run_state: lastRunState,
    repository_status: coverageBlocked ? "protected" : "open",
    manual_action_required: coverageBlocked,
    auto_coverage_retry: AUTO_COVERAGE_RETRY_ENABLED ? "enabled" : "disabled",
  }

  return {
    pageTitle: "Mission Control",
    pageSubtitle: "From Jira user story to tested Spring Boot code — with full traceability of every autonomous decision.",
    overallStatus: coverageBlocked ? "Blocked by Quality Gate" : "Run Successful",
    activeProject: "Auth Service",
    branch: "feature/test-improvement",
    summaryCards: buildSummaryCards(qualityGateStatus),
    timeline,
    runSummary: enrichedRun,
    narrative: buildNarrative(enrichedRun),
    graphRag: {
      domain: graphRagContext.domain,
      boundedContext: graphRagContext.bounded_context,
      patterns: graphRagContext.patterns,
      relatedEntities: graphRagContext.related_entities,
      businessRules: graphRagContext.business_rules,
      impactedFiles: [
        "AuthController.java",
        "AuthService.java",
        "UserRepository.java",
        "LoginRequest.java",
        "AuthServiceTest.java",
      ],
      injectedContext: JSON.stringify(graphRagContext, null, 2),
      confidence: "High",
    },
    agentActivity,
    agentArtifacts,
    agentChain,
    agentLogs,
    coverageGap,
    coverageRemediation,
    decisionJournal,
    nextActions,
    qualityCriteria,
    securityCheck,
    microcopy,
    generatedFiles,
    diagnostics,
  }
}
