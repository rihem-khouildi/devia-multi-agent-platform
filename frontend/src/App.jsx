import { Navigate, Route, Routes } from "react-router-dom"
import { AuthProvider } from "./context/AuthContext"
import { ThemeProvider } from "./context/ThemeContext"
import ProtectedRoute from "./components/ProtectedRoute"
import AppLayout from "./components/AppLayout"
import Login from "./pages/Login"
import Register from "./pages/Register"
import Dashboard from "./pages/Dashboard"
import Stories from "./pages/Stories"
import GraphRAG from "./pages/GraphRAG"
import Pipeline from "./pages/Pipeline"
import Placeholder from "./pages/Placeholder"
import RunQuality from "./pages/RunQuality"
import RunChanges from "./pages/RunChanges"
import RunLogs from "./pages/RunLogs"
import RunGitHub from "./pages/RunGitHub"
import RunErrors  from "./pages/RunErrors"
import RunMonitor from "./pages/RunMonitor"
import LivePipeline from "./pages/LivePipeline"
import AgentCollaboration from "./pages/AgentCollaboration"
import RunHistory from "./pages/RunHistory"
import ReplayMode from "./pages/ReplayMode"
import QualityCenter from "./pages/QualityCenter"
import NewRun from "./pages/NewRun"
import Projects from "./pages/Projects"
import Integrations from "./pages/Integrations"

export default function App() {
  return (
    <ThemeProvider>
    <AuthProvider>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Protected routes — all inside AppLayout */}
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<Dashboard />} />
          <Route path="/new-run" element={<NewRun />} />
          <Route path="/history" element={<RunHistory />} />
          <Route path="/stories" element={<Stories />} />
          <Route path="/graphrag" element={<GraphRAG />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/pipeline/:runId" element={<LivePipeline />} />
          <Route path="/agents/:runId" element={<AgentCollaboration />} />
          <Route path="/replay/:runId" element={<ReplayMode />} />
          <Route path="/changes" element={<RunChanges />} />
          <Route path="/quality" element={<RunQuality />} />
          <Route path="/quality/:runId" element={<QualityCenter />} />
          <Route path="/github" element={<RunGitHub />} />
          <Route path="/logs" element={<RunLogs />} />
          <Route path="/errors" element={<RunErrors />} />
          <Route
            path="/agent-activity"
            element={<Placeholder title="Agent Activity" description="Detailed agent-by-agent reasoning, prompts, and execution traces for each autonomous run." />}
          />
          <Route
            path="/generated-files"
            element={<Placeholder title="Generated Files" description="Artifact-level review workflows, diffs, and manual approvals for generated source and test files." />}
          />
          <Route path="/quality-gate" element={<RunQuality />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/monitor" element={<RunMonitor />} />
          <Route path="/settings" element={<Integrations />} />
          <Route path="/integrations" element={<Integrations />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
    </ThemeProvider>
  )
}
