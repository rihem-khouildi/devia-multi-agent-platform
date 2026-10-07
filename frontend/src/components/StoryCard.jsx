import { useMemo, useState } from "react"
import { MissionControlGlyph } from "./MissionControlIcons"
import { KEYWORD_TONES, parseStory } from "../lib/storyParser"

const PRIORITY_TONE = {
  highest: "border-rose-200 bg-rose-50 text-rose-700",
  high: "border-rose-200 bg-rose-50 text-rose-700",
  medium: "border-amber-200 bg-amber-50 text-amber-700",
  low: "border-emerald-200 bg-emerald-50 text-emerald-700",
  lowest: "border-emerald-200 bg-emerald-50 text-emerald-700",
}

function priorityTone(priority) {
  const key = String(priority || "").toLowerCase().trim()
  return PRIORITY_TONE[key] || "border-slate-200 bg-slate-50 text-slate-700"
}

function CountBadge({ icon, label, count, tone = "slate" }) {
  if (!count) return null
  const toneClass = KEYWORD_TONES[tone] || KEYWORD_TONES.slate
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${toneClass}`}>
      <MissionControlGlyph name={icon} className="h-3.5 w-3.5" />
      <span className="tabular-nums">{count}</span>
      <span className="font-medium">{label}</span>
    </span>
  )
}

function SectionHeader({ icon, title, count }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
          <MissionControlGlyph name={icon} className="h-3.5 w-3.5" />
        </span>
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      </div>
      {count !== undefined ? (
        <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
          {count}
        </span>
      ) : null}
    </div>
  )
}

function NumberedList({ items, accent = "indigo" }) {
  const accentClass = {
    indigo: "bg-indigo-50 text-indigo-700 border-indigo-100",
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-100",
    rose: "bg-rose-50 text-rose-700 border-rose-100",
  }[accent]

  return (
    <ol className="space-y-2">
      {items.map((item, index) => (
        <li
          key={`${index}-${item.slice(0, 24)}`}
          className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-white px-3 py-2.5 shadow-sm"
        >
          <span className={`mt-0.5 inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded-full border px-2 text-[11px] font-semibold tabular-nums ${accentClass}`}>
            {index + 1}
          </span>
          <span className="min-w-0 break-words text-sm leading-6 text-slate-600">{item}</span>
        </li>
      ))}
    </ol>
  )
}

export default function StoryCard({ story }) {
  const [expanded, setExpanded] = useState(false)
  const parsed = useMemo(() => parseStory(story), [story])

  const acCount = parsed.acceptanceCriteria.length
  const tcCount = parsed.testCases.length
  const fileCount = parsed.expectedFiles.length

  return (
    <article className="surface-card group rounded-[28px] transition-shadow hover:shadow-[0_24px_60px_rgba(15,23,42,0.08)]">
      <div className="flex flex-col gap-4 px-6 py-5">
        <header className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-600">
                <MissionControlGlyph name="stories" className="h-3.5 w-3.5" />
                {story.id}
              </span>
              <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${priorityTone(story.priority)}`}>
                <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
                {story.priority || "No priority"}
              </span>
              {story.story_points != null ? (
                <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700">
                  {story.story_points} pts
                </span>
              ) : null}
              {story.epic ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-[11px] font-semibold text-indigo-700">
                  <MissionControlGlyph name="graph" className="h-3.5 w-3.5" />
                  {story.epic}
                </span>
              ) : null}
            </div>
            <h2 className="mt-3 text-lg font-semibold leading-snug tracking-tight text-slate-900">
              {story.title}
            </h2>
          </div>

          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
            aria-expanded={expanded}
          >
            <MissionControlGlyph name={expanded ? "blocked" : "arrow"} className="h-3.5 w-3.5" />
            {expanded ? "Hide details" : "View details"}
          </button>
        </header>

        <p className="line-clamp-3 text-sm leading-6 text-slate-600">
          {parsed.preview || "No description available."}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <CountBadge icon="success" label={acCount === 1 ? "criterion" : "criteria"} count={acCount} tone="emerald" />
          <CountBadge icon="target" label={tcCount === 1 ? "test case" : "test cases"} count={tcCount} tone="indigo" />
          <CountBadge icon="file" label={fileCount === 1 ? "file" : "files"} count={fileCount} tone="slate" />
          {parsed.keywords.slice(0, 5).map((chip) => (
            <span
              key={chip.token}
              className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium ${KEYWORD_TONES[chip.tone] || KEYWORD_TONES.slate}`}
            >
              {chip.token}
            </span>
          ))}
        </div>

        {expanded ? (
          <div className="mt-2 grid gap-4 rounded-[24px] border border-slate-100 bg-slate-50/60 p-5 lg:grid-cols-2">
            <section className="lg:col-span-2">
              <SectionHeader icon="book" title="Description" />
              {parsed.description ? (
                <p className="whitespace-pre-line rounded-2xl border border-slate-100 bg-white px-4 py-3 text-sm leading-6 text-slate-600">
                  {parsed.description}
                </p>
              ) : (
                <p className="text-xs italic text-slate-500">No additional description.</p>
              )}
            </section>

            <section>
              <SectionHeader icon="success" title="Acceptance Criteria" count={acCount} />
              {acCount ? (
                <NumberedList items={parsed.acceptanceCriteria} accent="emerald" />
              ) : (
                <p className="rounded-2xl border border-dashed border-slate-200 bg-white px-3 py-2 text-xs italic text-slate-500">
                  No acceptance criteria parsed.
                </p>
              )}
            </section>

            <section>
              <SectionHeader icon="target" title="Test Cases" count={tcCount} />
              {tcCount ? (
                <NumberedList items={parsed.testCases} accent="indigo" />
              ) : (
                <p className="rounded-2xl border border-dashed border-slate-200 bg-white px-3 py-2 text-xs italic text-slate-500">
                  No test cases declared.
                </p>
              )}
            </section>

            <section className="lg:col-span-2">
              <SectionHeader icon="file" title="Expected Files" count={fileCount} />
              {fileCount ? (
                <div className="flex flex-wrap gap-2">
                  {parsed.expectedFiles.map((file) => (
                    <span
                      key={file}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm"
                    >
                      <MissionControlGlyph name="file" className="h-3.5 w-3.5 text-slate-500" />
                      {file}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="rounded-2xl border border-dashed border-slate-200 bg-white px-3 py-2 text-xs italic text-slate-500">
                  No expected files listed.
                </p>
              )}
            </section>

            {(story.labels || []).length ? (
              <section className="lg:col-span-2">
                <SectionHeader icon="graph" title="Labels" count={story.labels.length} />
                <div className="flex flex-wrap gap-2">
                  {story.labels.map((label) => (
                    <span
                      key={label}
                      className="inline-flex items-center rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-medium text-slate-700"
                    >
                      {label}
                    </span>
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  )
}
