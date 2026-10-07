import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import PageHeader from "../components/PageHeader"
import SectionCard from "../components/SectionCard"
import StoryCard from "../components/StoryCard"
import { MissionControlGlyph } from "../components/MissionControlIcons"
import { api } from "../lib/api"

const PRIORITY_FILTERS = [
  { key: "all", label: "All" },
  { key: "highest", label: "Highest" },
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
]

export default function Stories() {
  const storiesQuery = useQuery({ queryKey: ["stories"], queryFn: api.stories.list })
  const stories = storiesQuery.data?.stories || []

  const [search, setSearch] = useState("")
  const [priorityFilter, setPriorityFilter] = useState("all")

  const filteredStories = useMemo(() => {
    const term = search.trim().toLowerCase()
    return stories.filter((story) => {
      const priorityMatch =
        priorityFilter === "all" ||
        String(story.priority || "").toLowerCase() === priorityFilter
      if (!priorityMatch) return false

      if (!term) return true
      const haystack = [story.id, story.title, story.description, story.epic]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
      return haystack.includes(term)
    })
  }, [stories, search, priorityFilter])

  return (
    <div className="app-page">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <PageHeader
          eyebrow="Backlog"
          title="User stories"
          description="Story records pulled from Jira. Use the Story ID to drive a pipeline run, expand a card to inspect acceptance criteria and test contract."
          meta={storiesQuery.isFetching ? "Loading stories…" : `${storiesQuery.data?.total ?? 0} stories available`}
          accentClass="text-[#00AEEF]"
        />

        {!storiesQuery.isLoading && !storiesQuery.error && stories.length > 0 ? (
          <SectionCard className="px-5 py-4">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <label className="relative flex w-full items-center lg:max-w-md">
                <MissionControlGlyph name="help" className="absolute left-3 h-4 w-4 text-slate-400" />
                <input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by ID, title, or description"
                  className="w-full rounded-2xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm text-slate-700 shadow-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                />
              </label>

              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                  Priority
                </span>
                {PRIORITY_FILTERS.map((filter) => {
                  const active = priorityFilter === filter.key
                  return (
                    <button
                      key={filter.key}
                      type="button"
                      onClick={() => setPriorityFilter(filter.key)}
                      className={`rounded-full border px-3 py-1.5 text-[11px] font-semibold transition ${
                        active
                          ? "border-slate-900 bg-slate-900 text-white"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                      }`}
                    >
                      {filter.label}
                    </button>
                  )
                })}
              </div>
            </div>
          </SectionCard>
        ) : null}

        {storiesQuery.isLoading ? (
          <SectionCard className="p-6 text-sm text-slate-600">Loading stories from the backend…</SectionCard>
        ) : null}

        {storiesQuery.error ? (
          <SectionCard className="border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
            {storiesQuery.error.message || "Failed to load stories"}
          </SectionCard>
        ) : null}

        {!storiesQuery.isLoading && !storiesQuery.error && stories.length === 0 ? (
          <SectionCard className="p-8">
            <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center">
              <div className="text-lg font-medium text-slate-900">No stories returned</div>
              <p className="mt-2 text-sm text-slate-500">
                The backend responded successfully but there are no stories to show right now.
              </p>
            </div>
          </SectionCard>
        ) : null}

        {!storiesQuery.isLoading && !storiesQuery.error && stories.length > 0 ? (
          filteredStories.length ? (
            <div className="grid gap-4">
              {filteredStories.map((story) => (
                <StoryCard key={story.id} story={story} />
              ))}
            </div>
          ) : (
            <SectionCard className="p-8 text-center text-sm text-slate-500">
              No stories match the current filters.
            </SectionCard>
          )
        ) : null}
      </div>
    </div>
  )
}
