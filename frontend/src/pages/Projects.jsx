import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import PageHeader from "../components/PageHeader"
import SectionCard from "../components/SectionCard"
import { api } from "../lib/api"

function formatDate(iso) {
  if (!iso) return "—"
  return new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })
}

function FileIcon() {
  return (
    <svg className="h-4 w-4 shrink-0 text-slate-400" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M4 2h6l3 3v9H4V2z" /><path d="M10 2v3h3" />
    </svg>
  )
}

function FolderIcon({ open }) {
  return (
    <svg className="h-4 w-4 shrink-0 text-[#5B5CFF]" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      {open
        ? <path d="M1 5h14v8H1V5zM1 5l2-3h4l1 2h6" />
        : <path d="M1 5h14v8H1V5zM1 5l2-3h4l1 2" />}
    </svg>
  )
}

function TreeNode({ node, depth = 0 }) {
  const [open, setOpen] = useState(depth < 2)
  const isDir = node.type === "directory"

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm transition-colors ${isDir ? "cursor-pointer hover:bg-slate-100" : "text-slate-600"}`}
        style={{ paddingLeft: `${8 + depth * 20}px` }}
        onClick={isDir ? () => setOpen((v) => !v) : undefined}
      >
        {isDir ? (
          <>
            <span className="w-3 text-[10px] text-slate-400 select-none">{open ? "▾" : "▸"}</span>
            <FolderIcon open={open} />
          </>
        ) : (
          <>
            <span className="w-3" />
            <FileIcon />
          </>
        )}
        <span className={isDir ? "font-medium text-slate-800" : ""}>{node.name}</span>
      </div>
      {isDir && open && node.children?.map((child) => (
        <TreeNode key={child.path} node={child} depth={depth + 1} />
      ))}
    </div>
  )
}

function ProjectTree({ projectName }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["project-tree", projectName],
    queryFn: () => api.projects.tree(projectName),
    staleTime: 60_000,
  })

  if (isLoading) return <div className="px-4 py-3 text-sm text-slate-500">Loading tree…</div>
  if (isError) return (
    <div className="px-4 py-3 text-sm text-rose-600">{error?.message || "Failed to load project tree."}</div>
  )
  if (!data) return null

  return (
    <div className="max-h-96 overflow-y-auto px-2 py-2">
      {data.children?.map((child) => (
        <TreeNode key={child.path} node={child} depth={0} />
      ))}
    </div>
  )
}

export default function Projects() {
  const [expandedProject, setExpandedProject] = useState(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["projects-generated"],
    queryFn: api.projects.generated,
    staleTime: 30_000,
  })

  const projects = data?.projects ?? []

  function toggleProject(name) {
    setExpandedProject((current) => (current === name ? null : name))
  }

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <PageHeader
          eyebrow="Projects"
          title="Generated Projects"
          description="Projects produced by DEVIA runs, stored in the output folder. Click a project to browse its file tree."
          meta={isLoading ? "Loading…" : `${projects.length} project${projects.length !== 1 ? "s" : ""} found`}
          accentClass="text-[#5B5CFF]"
        />

        <div className="flex flex-wrap gap-3">
          <Link to="/new-run" className="btn-primary">New Run</Link>
        </div>

        {isError && (
          <SectionCard className="border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            Failed to load projects. Make sure the backend is running.
          </SectionCard>
        )}

        {!isLoading && !isError && projects.length === 0 && (
          <SectionCard className="p-8 text-center">
            <div className="text-sm font-medium text-slate-900">No projects yet</div>
            <p className="mt-2 text-sm text-slate-500">
              Launch a DEVIA run to generate your first project in the output folder.
            </p>
            <Link to="/new-run" className="btn-primary mt-4 inline-block">
              Launch a Run
            </Link>
          </SectionCard>
        )}

        {projects.length > 0 && (
          <SectionCard className="overflow-hidden">
            <div className="border-b border-slate-200 px-6 py-4">
              <h2 className="text-base font-medium text-slate-900">Output projects</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {projects.map((project) => (
                <div key={project.path}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between px-6 py-4 hover:bg-slate-50 transition-colors text-left"
                    onClick={() => toggleProject(project.name)}
                  >
                    <div className="flex items-center gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,_rgba(91,92,255,0.12)_0%,_rgba(0,174,239,0.12)_100%)] text-xs font-semibold text-[#5B5CFF]">
                        {project.name.slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-slate-900">{project.name}</div>
                        <div className="mt-0.5 text-xs text-slate-500 font-mono">{project.relative_path}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-6 text-sm text-slate-500">
                      <div className="text-right">
                        <div className="text-xs text-slate-400">Last updated</div>
                        <div className="font-medium text-slate-700">{formatDate(project.updated_at)}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-slate-400">Items</div>
                        <div className="font-medium text-slate-700">{project.runs_count}</div>
                      </div>
                      <span className="text-slate-400 text-xs">{expandedProject === project.name ? "▲ Hide" : "▼ Explore"}</span>
                    </div>
                  </button>

                  {expandedProject === project.name && (
                    <div className="border-t border-slate-100 bg-slate-50 px-4 pb-4 pt-2">
                      <div className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">File tree</div>
                      <ProjectTree projectName={project.name} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </SectionCard>
        )}
      </div>
    </div>
  )
}
