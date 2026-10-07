import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "./api"

export function useRunsQuery() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: api.runs.list,
    refetchInterval: (query) => {
      const runs = query.state.data?.runs || []
      return runs.some((run) => run.status === "running") ? 5000 : false
    },
  })
}

export function useRunSummaryQuery(runId) {
  return useQuery({
    queryKey: ["runs", runId],
    queryFn: () => api.runs.get(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => (
      query.state.data?.status === "running" ? 5000 : false
    ),
  })
}

export function useRunErrorsQuery(runId) {
  return useQuery({
    queryKey: ["runs", runId, "errors"],
    queryFn: () => api.runs.errors(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      return query.state.data !== undefined ? false : 5000
    },
  })
}

export function useRunEventsQuery(runId, runStatus) {
  return useQuery({
    queryKey: ["runs", runId, "events"],
    queryFn: () => api.runs.events(runId),
    enabled: Boolean(runId),
    // Poll every 2s while running, stop once the run reaches a terminal state
    refetchInterval: () => {
      if (!runStatus || runStatus === "running") return 2000
      return false
    },
  })
}

export function useDefaultRunId(runs) {
  const [selectedRunId, setSelectedRunId] = useState("")

  useEffect(() => {
    if (!runs.length) {
      setSelectedRunId("")
      return
    }
    setSelectedRunId((current) => {
      if (current && runs.some((run) => run.run_id === current)) {
        return current
      }
      return runs[0].run_id
    })
  }, [runs])

  return [selectedRunId, setSelectedRunId]
}
