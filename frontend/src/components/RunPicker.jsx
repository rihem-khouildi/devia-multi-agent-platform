import SectionCard from "./SectionCard"

export default function RunPicker({
  title = "Run selection",
  description = "Choose a run to inspect.",
  runs = [],
  selectedRunId,
  onChange,
  loading = false,
}) {
  return (
    <SectionCard>
      <div className="border-b border-slate-200 px-6 py-5">
        <h2 className="text-lg font-medium text-slate-900">{title}</h2>
        <p className="mt-1 text-sm text-slate-500">{description}</p>
      </div>
      <div className="space-y-4 px-6 py-5">
        <select
          value={selectedRunId}
          onChange={(event) => onChange(event.target.value)}
          className="field-input"
          disabled={loading || runs.length === 0}
        >
          {runs.length === 0 ? <option value="">No runs available</option> : null}
          {runs.map((run) => (
            <option key={run.run_id} value={run.run_id}>
              {run.story_id} - {run.story_title || run.run_id}
            </option>
          ))}
        </select>
        <div className="text-xs text-slate-500">
          {loading ? "Refreshing runs..." : `${runs.length} selectable run(s)`}
        </div>
      </div>
    </SectionCard>
  )
}
