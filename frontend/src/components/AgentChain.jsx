import { MissionControlGlyph } from "./MissionControlIcons"

const toneStyles = {
  success: {
    ring: "ring-emerald-200",
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
    dot: "bg-emerald-500",
    iconShell: "bg-emerald-50 text-emerald-600",
    line: "from-emerald-300 via-emerald-200 to-emerald-200",
  },
  warning: {
    ring: "ring-amber-200",
    badge: "bg-amber-50 text-amber-700 border-amber-200",
    dot: "bg-amber-500",
    iconShell: "bg-amber-50 text-amber-600",
    line: "from-amber-300 via-amber-200 to-rose-200",
  },
  blocked: {
    ring: "ring-rose-300",
    badge: "bg-rose-50 text-rose-700 border-rose-200",
    dot: "bg-rose-500",
    iconShell: "bg-rose-50 text-rose-600",
    line: "from-rose-300 via-rose-200 to-rose-100",
  },
  pending: {
    ring: "ring-slate-200",
    badge: "bg-slate-100 text-slate-600 border-slate-200",
    dot: "bg-slate-400",
    iconShell: "bg-slate-50 text-slate-500",
    line: "from-slate-200 via-slate-100 to-slate-100",
  },
}

export default function AgentChain({ chain }) {
  return (
    <div className="space-y-4">
      <div className="scrollbar-soft overflow-x-auto pb-2">
        <div className="flex min-w-max items-stretch gap-3">
          {chain.map((agent, index) => {
            const tone = toneStyles[agent.status] || toneStyles.pending
            const next = chain[index + 1]
            const nextTone = next ? toneStyles[next.status] || toneStyles.pending : null

            return (
              <div key={agent.key} className="flex items-stretch">
                <div
                  className={`mission-chain-card relative flex w-56 flex-col rounded-[22px] border bg-white p-4 shadow-sm ring-1 ${tone.ring} ${
                    agent.status === "blocked"
                      ? "border-rose-200"
                      : agent.status === "warning"
                      ? "border-amber-200"
                      : "border-slate-200"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${tone.iconShell}`}>
                      <MissionControlGlyph name={agent.icon} className="h-4 w-4" />
                    </span>
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                        Step {index + 1}
                      </div>
                      <div className="text-sm font-semibold text-slate-900">{agent.name}</div>
                    </div>
                  </div>
                  <p className="mt-3 text-xs leading-5 text-slate-500">{agent.role}</p>
                  <div className="mt-3 flex items-center justify-between gap-2 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                    <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                      Output
                    </span>
                    <span className="truncate text-[11px] font-semibold text-slate-700" title={agent.artifact}>
                      {agent.artifact}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] ${tone.badge}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
                      {agent.status}
                    </span>
                    {agent.status === "blocked" ? (
                      <MissionControlGlyph name="lock" className="h-4 w-4 text-rose-500" />
                    ) : null}
                  </div>
                </div>
                {next ? (
                  <div className="flex w-10 items-center justify-center">
                    <div className={`h-px w-full bg-gradient-to-r ${nextTone?.line || tone.line}`} />
                    <MissionControlGlyph name="arrow" className="-ml-3 h-4 w-4 text-slate-400" />
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      </div>

      <p className="text-xs leading-6 text-slate-500">
        Each agent receives the previous artifact, makes one decision, and hands off. The chain ends at the
        Quality Gate, which is the only agent allowed to push to GitHub.
      </p>
    </div>
  )
}
