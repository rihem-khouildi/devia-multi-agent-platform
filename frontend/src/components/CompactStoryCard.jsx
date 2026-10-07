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

function CountChip({ icon, count, label, tone = "slate" }) {
  if (!count) return null
  const toneClass = KEYWORD_TONES[tone] || KEYWORD_TONES.slate
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${toneClass}`}>
      <MissionControlGlyph name={icon} className="h-3 w-3" />
      <span className="tabular-nums">{count}</span>
      <span className="font-medium opacity-80">{label}</span>
    </span>
  )
}

function NumberedList({ items, accent = "indigo" }) {
  const accentClass = {
    indigo: "bg-indigo-50 text-indigo-700 border-indigo-100",
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-100",
  }[accent]

  return (
    <ol className="space-y-1.5">
      {items.map((item, index) => (
        <li
          key={`${index}-${item.slice(0, 24)}`}
          className="flex items-start gap-2 rounded-xl border border-slate-100 bg-white px-2.5 py-1.5"
        >
          <span className={`mt-0.5 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full border px-1.5 text-[10px] font-semibold tabular-nums ${accentClass}`}>
            {index + 1}
          </span>
          <span className="min-w-0 break-words text-[12.5px] leading-5 text-slate-600">{item}</span>
        </li>
      ))}
    </ol>
  )
}

export default function CompactStoryCard({ story, isSelected, onSelect, graphLoaded }) {
  const [expanded, setExpanded] = useState(false)
  const parsed = useMemo(() => parseStory(story), [story])

  const acCount = parsed.acceptanceCriteria.length
  const tcCount = parsed.testCases.length
  const fileCount = parsed.expectedFiles.length

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect?.(story)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault()
          onSelect?.(story)
        }
      }}
      className={`group relative flex h-full cursor-pointer flex-col gap-3 rounded-[24px] border bg-white p-4 text-left shadow-sm transition ${
        isSelected
          ? "border-indigo-300 bg-indigo-50/60 ring-2 ring-indigo-200"
          : "border-slate-200 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-600">
              <MissionControlGlyph name="stories" className="h-3 w-3" />
              {story.id}
            </span>
            <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${priorityTone(story.priority)}`}>
              <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
              {story.priority || "No priority"}
            </span>
            {story.story_points != null ? (
              <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-semibold text-slate-700">
                {story.story_points} pts
              </span>
            ) : null}
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${
                graphLoaded
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }`}
            >
              <MissionControlGlyph name={graphLoaded ? "graph" : "warning"} className="h-3 w-3" />
              GraphRAG {graphLoaded ? "Ready" : "Not loaded"}
            </span>
          </div>
          <h3 className="mt-2 line-clamp-2 text-[15px] font-semibold leading-snug tracking-tight text-slate-900">
            {story.title}
          </h3>
        </div>
        {isSelected ? (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-indigo-600 px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-[0.16em] text-white shadow-sm">
            <MissionControlGlyph name="success" className="h-3 w-3" />
            Selected
          </span>
        ) : null}
      </div>

      <p className="line-clamp-2 text-[12.5px] leading-5 text-slate-600">
        {parsed.preview || "No description available."}
      </p>

      <div className="mt-auto flex flex-wrap items-center gap-1.5">
        <CountChip icon="success" count={acCount} label={acCount === 1 ? "criterion" : "criteria"} tone="emerald" />
        <CountChip icon="target" count={tcCount} label={tcCount === 1 ? "test" : "tests"} tone="indigo" />
        <CountChip icon="file" count={fileCount} label={fileCount === 1 ? "file" : "files"} tone="slate" />
        {parsed.keywords.slice(0, 3).map((chip) => (
          <span
            key={chip.token}
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] font-medium ${KEYWORD_TONES[chip.tone] || KEYWORD_TONES.slate}`}
          >
            {chip.token}
          </span>
        ))}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
        <span className={`inline-flex items-center gap-1 text-[11px] font-semibold ${isSelected ? "text-indigo-700" : "text-slate-500"}`}>
          <MissionControlGlyph name={isSelected ? "success" : "arrow"} className="h-3.5 w-3.5" />
          {isSelected ? "Story selected for run" : "Click to select"}
        </span>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            setExpanded((value) => !value)
          }}
          className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10.5px] font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
          aria-expanded={expanded}
        >
          <MissionControlGlyph name={expanded ? "blocked" : "help"} className="h-3 w-3" />
          {expanded ? "Hide details" : "View details"}
        </button>
      </div>

      {expanded ? (
        <div
          onClick={(event) => event.stopPropagation()}
          className="grid gap-3 rounded-2xl border border-slate-100 bg-slate-50/70 p-3"
        >
          {parsed.description ? (
            <section>
              <div className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                <MissionControlGlyph name="book" className="h-3 w-3" />
                Description
              </div>
              <p className="whitespace-pre-line rounded-xl border border-slate-100 bg-white px-3 py-2 text-[12.5px] leading-5 text-slate-600">
                {parsed.description}
              </p>
            </section>
          ) : null}

          {acCount ? (
            <section>
              <div className="mb-1.5 flex items-center justify-between text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                <span className="flex items-center gap-1.5">
                  <MissionControlGlyph name="success" className="h-3 w-3" />
                  Acceptance Criteria
                </span>
                <span className="rounded-full border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-500">
                  {acCount}
                </span>
              </div>
              <NumberedList items={parsed.acceptanceCriteria} accent="emerald" />
            </section>
          ) : null}

          {tcCount ? (
            <section>
              <div className="mb-1.5 flex items-center justify-between text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                <span className="flex items-center gap-1.5">
                  <MissionControlGlyph name="target" className="h-3 w-3" />
                  Test Cases
                </span>
                <span className="rounded-full border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-500">
                  {tcCount}
                </span>
              </div>
              <NumberedList items={parsed.testCases} accent="indigo" />
            </section>
          ) : null}

          {fileCount ? (
            <section>
              <div className="mb-1.5 flex items-center justify-between text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                <span className="flex items-center gap-1.5">
                  <MissionControlGlyph name="file" className="h-3 w-3" />
                  Expected Files
                </span>
                <span className="rounded-full border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-500">
                  {fileCount}
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {parsed.expectedFiles.map((file) => (
                  <span
                    key={file}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700"
                  >
                    <MissionControlGlyph name="file" className="h-3 w-3 text-slate-500" />
                    {file}
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          {!parsed.description && !acCount && !tcCount && !fileCount ? (
            <p className="rounded-xl border border-dashed border-slate-200 bg-white px-3 py-2 text-[11.5px] italic text-slate-500">
              No structured details parsed for this story.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
