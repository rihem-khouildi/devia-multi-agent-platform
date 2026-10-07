import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Settings,
  Ticket,
  GitBranch,
  CheckCircle2,
  XCircle,
  Eye,
  EyeOff,
  Save,
  Plug,
  AlertTriangle,
} from "lucide-react"
import { api } from "../lib/api"

const MASKED = "••••••••configured"

// ── Token input — shows masked placeholder after save ─────────────────────────
function TokenInput({ id, label, placeholder, value, onChange, showToggle = true }) {
  const [visible, setVisible] = useState(false)
  const isMasked = value === MASKED

  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-slate-700 mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={visible && !isMasked ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={isMasked ? "Leave blank to keep existing token" : placeholder}
          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 pr-10 text-sm text-slate-900 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        />
        {showToggle && !isMasked && (
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            tabIndex={-1}
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
        {isMasked && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-emerald-500">
            <CheckCircle2 className="h-4 w-4" />
          </span>
        )}
      </div>
      {isMasked && (
        <p className="mt-1 text-xs text-slate-400">Token configured — leave blank to keep, or type a new one to replace.</p>
      )}
    </div>
  )
}

// ── Status banner ─────────────────────────────────────────────────────────────
function Banner({ type, message }) {
  if (!message) return null
  const styles = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    error: "border-rose-200 bg-rose-50 text-rose-800",
    info: "border-blue-200 bg-blue-50 text-blue-800",
  }
  const icons = {
    success: <CheckCircle2 className="h-4 w-4 shrink-0" />,
    error: <XCircle className="h-4 w-4 shrink-0" />,
    info: <AlertTriangle className="h-4 w-4 shrink-0" />,
  }
  return (
    <div className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium ${styles[type]}`}>
      {icons[type]}
      {message}
    </div>
  )
}

// ── Field row ─────────────────────────────────────────────────────────────────
function Field({ id, label, value, onChange, placeholder, type = "text" }) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
      />
    </div>
  )
}

// ── Section card ──────────────────────────────────────────────────────────────
function IntegrationCard({ icon: Icon, title, description, accent, children, onTest, testLabel, testLoading, testResult }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-3 border-b border-slate-100 px-6 py-4">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${accent}`}>
          <Icon className="h-5 w-5 text-white" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <p className="text-xs text-slate-500">{description}</p>
        </div>
      </div>
      <div className="space-y-4 px-6 py-5">
        {children}
        {testResult && (
          <Banner
            type={testResult.success ? "success" : "error"}
            message={testResult.message}
          />
        )}
        <button
          type="button"
          onClick={onTest}
          disabled={testLoading}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50 transition"
        >
          <Plug className="h-3.5 w-3.5" />
          {testLoading ? "Testing…" : testLabel}
        </button>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Integrations() {
  const queryClient = useQueryClient()

  // ── Remote config ─────────────────────────────────────────────────────────
  const { data, isLoading } = useQuery({
    queryKey: ["integrations"],
    queryFn: api.integrations.get,
    staleTime: 60_000,
  })

  // ── Local form state ──────────────────────────────────────────────────────
  const [jiraUrl, setJiraUrl] = useState("")
  const [jiraUsername, setJiraUsername] = useState("")
  const [jiraToken, setJiraToken] = useState("")
  const [jiraProjectKey, setJiraProjectKey] = useState("")

  const [githubOwner, setGithubOwner] = useState("")
  const [githubRepo, setGithubRepo] = useState("")
  const [githubToken, setGithubToken] = useState("")

  const [saveStatus, setSaveStatus] = useState(null)    // null | "success" | "error"
  const [saveMessage, setSaveMessage] = useState("")

  const [jiraTestResult, setJiraTestResult] = useState(null)
  const [githubTestResult, setGithubTestResult] = useState(null)

  // Populate form from remote data (mask tokens)
  useEffect(() => {
    if (!data) return
    const j = data.jira ?? {}
    const g = data.github ?? {}
    setJiraUrl(j.jira_url ?? "")
    setJiraUsername(j.jira_username ?? "")
    setJiraToken(j.jira_api_token ?? "")          // already masked by backend
    setJiraProjectKey(j.jira_project_key ?? "")
    setGithubOwner(g.github_owner ?? "")
    setGithubRepo(g.github_repo ?? "")
    setGithubToken(g.github_token ?? "")           // already masked by backend
  }, [data])

  // ── Save mutation ─────────────────────────────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: () =>
      api.integrations.save({
        jira_url: jiraUrl || null,
        jira_username: jiraUsername || null,
        jira_api_token: jiraToken === MASKED ? null : (jiraToken || null),
        jira_project_key: jiraProjectKey || null,
        github_owner: githubOwner || null,
        github_repo: githubRepo || null,
        github_token: githubToken === MASKED ? null : (githubToken || null),
      }),
    onSuccess: () => {
      setSaveStatus("success")
      setSaveMessage("Configuration saved successfully.")
      queryClient.invalidateQueries({ queryKey: ["integrations"] })
      queryClient.invalidateQueries({ queryKey: ["health"] })
      // Re-mask tokens in local state
      if (jiraToken && jiraToken !== MASKED) setJiraToken(MASKED)
      if (githubToken && githubToken !== MASKED) setGithubToken(MASKED)
    },
    onError: (err) => {
      setSaveStatus("error")
      setSaveMessage(err.message || "Failed to save configuration.")
    },
  })

  // ── Test mutations ────────────────────────────────────────────────────────
  const [jiraTestLoading, setJiraTestLoading] = useState(false)
  const [githubTestLoading, setGithubTestLoading] = useState(false)

  async function handleTestJira() {
    setJiraTestLoading(true)
    setJiraTestResult(null)
    try {
      const res = await api.integrations.testJira()
      setJiraTestResult({ success: true, message: res.message })
    } catch (err) {
      setJiraTestResult({ success: false, message: err.message || "Jira connection failed." })
    } finally {
      setJiraTestLoading(false)
    }
  }

  async function handleTestGitHub() {
    setGithubTestLoading(true)
    setGithubTestResult(null)
    try {
      const res = await api.integrations.testGitHub()
      setGithubTestResult({ success: true, message: res.message })
    } catch (err) {
      setGithubTestResult({ success: false, message: err.message || "GitHub connection failed." })
    } finally {
      setGithubTestLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="app-page">
        <div className="mx-auto flex w-full max-w-3xl items-center gap-2 pt-10 text-sm text-slate-500">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
          Loading integration settings…
        </div>
      </div>
    )
  }

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">

        {/* Header */}
        <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50">
              <Settings className="h-5 w-5 text-indigo-600" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900">Integrations</h1>
            </div>
          </div>
        </div>

        {/* Save banner */}
        {saveStatus && <Banner type={saveStatus} message={saveMessage} />}

        {/* ── Cartes côte à côte ────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2">

          {/* Jira */}
          <IntegrationCard
            icon={Ticket}
            title="Jira Integration"
            description="Used to fetch user stories for pipeline execution"
            accent="bg-blue-600"
            onTest={handleTestJira}
            testLabel="Test Jira Connection"
            testLoading={jiraTestLoading}
            testResult={jiraTestResult}
          >
            <Field id="jira-url" label="Jira URL" value={jiraUrl} onChange={setJiraUrl}
              placeholder="https://yourcompany.atlassian.net" />
            <Field id="jira-username" label="Jira Email / Username" value={jiraUsername}
              onChange={setJiraUsername} placeholder="you@company.com" />
            <TokenInput id="jira-token" label="Jira API Token" value={jiraToken}
              onChange={setJiraToken} placeholder="ATATT3xFf…" />
            <Field id="jira-key" label="Project Key" value={jiraProjectKey}
              onChange={setJiraProjectKey} placeholder="PROJ" />
          </IntegrationCard>

          {/* GitHub */}
          <IntegrationCard
            icon={GitBranch}
            title="GitHub Integration"
            description="Used to commit generated code and open pull requests"
            accent="bg-slate-800"
            onTest={handleTestGitHub}
            testLabel="Test GitHub Connection"
            testLoading={githubTestLoading}
            testResult={githubTestResult}
          >
            <Field id="gh-owner" label="GitHub Owner (user or org)" value={githubOwner}
              onChange={setGithubOwner} placeholder="your-org" />
            <Field id="gh-repo" label="Repository Name" value={githubRepo}
              onChange={setGithubRepo} placeholder="my-spring-project" />
            <TokenInput id="gh-token" label="GitHub Personal Access Token" value={githubToken}
              onChange={setGithubToken} placeholder="ghp_…" />
          </IntegrationCard>

        </div>

        {/* Save button */}
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => { setSaveStatus(null); saveMutation.mutate() }}
            disabled={saveMutation.isPending}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-8 py-3 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 transition"
          >
            <Save className="h-4 w-4" />
            {saveMutation.isPending ? "Saving…" : "Save Configuration"}
          </button>
        </div>

      </div>
    </div>
  )
}
