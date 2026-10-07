export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

if (import.meta.env.DEV) {
  console.log("[api] API_BASE_URL →", API_BASE_URL)
}

const TOKEN_KEY = "devia_auth_token"

class ApiError extends Error {
  constructor(status, payload, fallbackMessage) {
    super(payload?.detail || payload?.error || fallbackMessage || `Request failed with status ${status}`)
    this.name = "ApiError"
    this.status = status
    this.payload = payload
  }
}

async function req(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers = { "Content-Type": "application/json", ...options.headers }
  if (token) headers["Authorization"] = `Bearer ${token}`

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })

  const contentType = response.headers.get("content-type") || ""
  const isJson = contentType.includes("application/json")
  const payload = isJson ? await response.json().catch(() => null) : await response.text().catch(() => "")

  if (response.status === 401) {
    // Token expired — clear storage and redirect to login
    localStorage.removeItem(TOKEN_KEY)
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login"
    }
    throw new ApiError(401, payload, "Session expired. Please log in again.")
  }

  if (!response.ok) {
    throw new ApiError(response.status, payload, response.statusText)
  }

  return payload
}

// Multipart upload — no Content-Type header (browser sets it with boundary)
async function reqUpload(path, formData) {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers = {}
  if (token) headers["Authorization"] = `Bearer ${token}`

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: formData,
  })

  const contentType = response.headers.get("content-type") || ""
  const isJson = contentType.includes("application/json")
  const payload = isJson ? await response.json().catch(() => null) : await response.text().catch(() => "")

  if (response.status === 401) {
    localStorage.removeItem(TOKEN_KEY)
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login"
    }
    throw new ApiError(401, payload, "Session expired.")
  }

  if (!response.ok) {
    throw new ApiError(response.status, payload, response.statusText)
  }

  return payload
}

const startRun = (body) => req("/runs", { method: "POST", body: JSON.stringify(body) })
const getTargetProject = () => req("/projects/target")
const validateTargetProject = () => req("/projects/target/validate", { method: "POST" })
const getValidationJob = (jobId) => req(`/projects/target/validate/${jobId}`)

export const api = {
  startRun,
  getTargetProject,
  validateTargetProject,
  health: () => req("/health"),

  auth: {
    register: (username, email, password) =>
      req("/auth/register", { method: "POST", body: JSON.stringify({ username, email, password }) }),
    login: async (username, password) => {
      const body = new URLSearchParams({ username, password })
      const r = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      })
      const payload = await r.json().catch(() => null)
      if (!r.ok) throw new ApiError(r.status, payload, r.statusText)
      return payload
    },
    me: () => req("/auth/me"),
  },

  runs: {
    list: () => req("/runs"),
    get: (id) => req(`/runs/${id}`),
    create: startRun,
    quality: (id) => req(`/runs/${id}/quality`),
    changes: (id) => req(`/runs/${id}/changes`),
    logs: (id) => req(`/runs/${id}/logs`),
    github: (id) => req(`/runs/${id}/github`),
    errors:       (id) => req(`/runs/${id}/errors`),
    events:       (id) => req(`/runs/${id}/events`),
    files:        (id) => req(`/runs/${id}/files`),
    acceptFile:   (id, fileId) => req(`/runs/${id}/files/${fileId}/accept`,  { method: "POST" }),
    rejectFile:   (id, fileId) => req(`/runs/${id}/files/${fileId}/reject`,  { method: "POST" }),
    resetFile:    (id, fileId) => req(`/runs/${id}/files/${fileId}/reset`,   { method: "POST" }),
    triggerCommit:(id)         => req(`/runs/${id}/commit`,                  { method: "POST" }),
    llmFix:       (id, body)   => req(`/runs/${id}/llm-fix`,                 { method: "POST", body: JSON.stringify(body) }),
    llmFixStatus: (id)         => req(`/runs/${id}/llm-fix/status`),
  },

  stories: {
    list: () => req("/stories"),
    get: (id) => req(`/stories/${id}`),
  },

  projects: {
    list: () => req("/projects"),
    current: () => req("/projects/current"),
    target: getTargetProject,
    validateTarget: validateTargetProject,
    getValidationJob,
    generated: () => req("/projects/generated"),
    tree: (name) => req(`/projects/generated/${encodeURIComponent(name)}/tree`),
  },

  projectSources: {
    list: () => req("/projects/sources"),
    upload: (file) => {
      const fd = new FormData()
      fd.append("file", file)
      return reqUpload("/projects/sources/upload", fd)
    },
    delete: (name) => req(`/projects/sources/${encodeURIComponent(name)}`, { method: "DELETE" }),
    tree: (name) => req(`/projects/sources/${encodeURIComponent(name)}/tree`),
  },

  graphrag: {
    summary: () => req("/graphrag/summary"),
    status: () => req("/graphrag/status"),
    load: (path) => req("/graphrag/load", { method: "POST", body: JSON.stringify({ path }) }),
    upload: (file) => {
      const fd = new FormData()
      fd.append("file", file)
      return reqUpload("/graphrag/upload", fd)
    },
    loadDefault: () => req("/graphrag/load-default", { method: "POST" }),
    storyContext: (id) => req(`/graphrag/stories/${id}/context`),
    storySummary: (id) => req(`/graphrag/stories/${id}/summary`),
  },

  integrations: {
    get: () => req("/config/integrations"),
    save: (body) => req("/config/integrations", { method: "POST", body: JSON.stringify(body) }),
    testJira: () => req("/config/integrations/test-jira", { method: "POST" }),
    testGitHub: () => req("/config/integrations/test-github", { method: "POST" }),
  },
}
