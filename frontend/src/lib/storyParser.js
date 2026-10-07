const KEYWORD_CHIPS = [
  { token: "Controller", tone: "indigo" },
  { token: "Service", tone: "violet" },
  { token: "Repository", tone: "sky" },
  { token: "DTO", tone: "rose" },
  { token: "Entity", tone: "amber" },
  { token: "API", tone: "indigo" },
  { token: "REST", tone: "indigo" },
  { token: "Endpoint", tone: "indigo" },
  { token: "Test", tone: "emerald" },
  { token: "JaCoCo", tone: "emerald" },
  { token: "JWT", tone: "violet" },
  { token: "Security", tone: "rose" },
  { token: "Login", tone: "sky" },
  { token: "Auth", tone: "rose" },
  { token: "Database", tone: "amber" },
  { token: "Spring", tone: "emerald" },
  { token: "Maven", tone: "amber" },
  { token: "Coverage", tone: "emerald" },
  { token: "Validation", tone: "violet" },
]

const AC_LINE = /(^|\n)\s*(?:AC|Acceptance Criteria)\s*[#-]?\s*(\d+)\s*[:.\-)]\s*([^\n]+)/gi
const TC_LINE = /(^|\n)\s*(?:TC|Test Case)\s*[#-]?\s*(\d+)\s*[:.\-)]\s*([^\n]+)/gi
const SECTION_BLOCK = /(?:^|\n)\s*(?:#+\s*)?([A-Za-z][A-Za-z\s/]+?)\s*[:\n]+([\s\S]*?)(?=\n\s*(?:#+\s*)?[A-Z][A-Za-z\s/]+?\s*[:\n]|\s*$)/g

const FILE_PATTERN = /([A-Za-z][\w-]+(?:\.[A-Za-z][\w-]+)+(?:\/[\w.-]+)*)/g
const JAVA_FILE_PATTERN = /\b[A-Z][A-Za-z0-9_]*(?:Controller|Service|Repository|Test|DTO|Request|Response|Entity)\.java\b/g

function unique(values) {
  return Array.from(new Set(values.filter(Boolean).map((v) => v.trim())))
}

function extractEnumeratedItems(text, regex) {
  if (!text) return []
  const items = []
  let match
  const r = new RegExp(regex.source, regex.flags)
  while ((match = r.exec(text)) !== null) {
    const index = Number.parseInt(match[2], 10)
    const value = match[3]?.trim()
    if (value) items.push({ index, value })
  }
  return items
    .sort((a, b) => a.index - b.index)
    .map((item) => item.value)
}

function extractFromHeading(text, headingPatterns) {
  if (!text) return null
  for (const pattern of headingPatterns) {
    const re = new RegExp(`(?:^|\\n)\\s*(?:#+\\s*|\\*\\*)?${pattern}\\s*[:\\-]?\\s*\\n?([\\s\\S]*?)(?=\\n\\s*(?:#+\\s*|\\*\\*)?[A-Z][A-Za-z\\s/]+?\\s*[:\\-]?\\s*\\n|$)`, "i")
    const match = text.match(re)
    if (match && match[1]) return match[1].trim()
  }
  return null
}

function splitBulletList(text) {
  if (!text) return []
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.replace(/^[-*•·]\s+/, "").replace(/^\d+[.)]\s+/, ""))
    .filter(Boolean)
  return unique(lines)
}

function extractFiles(text) {
  if (!text) return []
  const filesSection = extractFromHeading(text, [
    "Expected Test Files",
    "Expected Files",
    "Files Expected",
    "Test Files",
    "Affected Files",
    "Generated Files",
  ])

  const files = new Set()
  if (filesSection) {
    splitBulletList(filesSection).forEach((line) => {
      const matches = line.match(FILE_PATTERN)
      if (matches) matches.forEach((m) => files.add(m))
      else files.add(line)
    })
  }

  const javaMatches = text.match(JAVA_FILE_PATTERN)
  if (javaMatches) javaMatches.forEach((m) => files.add(m))

  return Array.from(files)
}

function extractKeywords(text) {
  if (!text) return []
  const lower = text.toLowerCase()
  return KEYWORD_CHIPS.filter((chip) => lower.includes(chip.token.toLowerCase()))
}

function buildPreview(text, maxChars = 220) {
  if (!text) return ""
  const stripped = text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/AC\s*\d+\s*[:.\-)][^\n]*/gi, "")
    .replace(/TC\s*\d+\s*[:.\-)][^\n]*/gi, "")
    .replace(/(?:^|\n)\s*(?:Acceptance Criteria|Test Cases|Expected (?:Test )?Files)[:\s\S]*$/i, "")
    .replace(/\s+/g, " ")
    .trim()

  if (stripped.length <= maxChars) return stripped
  const cut = stripped.slice(0, maxChars)
  const lastSpace = cut.lastIndexOf(" ")
  return `${cut.slice(0, lastSpace > 80 ? lastSpace : maxChars)}…`
}

function cleanDescription(text) {
  if (!text) return ""
  // Strip the AC/TC/Files sections so the "Description" block is genuinely description.
  return text
    .replace(/(?:^|\n)\s*(?:Acceptance Criteria)[:\s][\s\S]*?(?=\n\s*(?:#+\s*|\*\*)?(?:Test Cases?|Expected (?:Test )?Files|$))/gi, "\n")
    .replace(/(?:^|\n)\s*(?:Test Cases?)[:\s][\s\S]*?(?=\n\s*(?:#+\s*|\*\*)?(?:Expected (?:Test )?Files|$))/gi, "\n")
    .replace(/(?:^|\n)\s*Expected (?:Test )?Files[:\s][\s\S]*$/gi, "")
    .replace(/AC\s*\d+\s*[:.\-)][^\n]*/gi, "")
    .replace(/TC\s*\d+\s*[:.\-)][^\n]*/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

export function parseStory(story) {
  const description = story?.description || ""

  const acFromList = Array.isArray(story?.acceptance_criteria) ? story.acceptance_criteria.filter(Boolean) : []
  const acFromText = extractEnumeratedItems(description, AC_LINE)
  let acceptanceCriteria = acFromList.length ? acFromList : acFromText

  if (!acceptanceCriteria.length) {
    const acSection = extractFromHeading(description, ["Acceptance Criteria"])
    if (acSection) acceptanceCriteria = splitBulletList(acSection)
  }

  let testCases = extractEnumeratedItems(description, TC_LINE)
  if (!testCases.length) {
    const tcSection = extractFromHeading(description, ["Test Cases", "Test Contract"])
    if (tcSection) testCases = splitBulletList(tcSection)
  }

  const expectedFiles = extractFiles(description)
  const keywords = extractKeywords([story?.title, description, ...(story?.labels || [])].join(" "))
  const preview = buildPreview(description) || story?.title || ""
  const cleanedDescription = cleanDescription(description)

  return {
    preview,
    description: cleanedDescription || description,
    acceptanceCriteria: unique(acceptanceCriteria),
    testCases: unique(testCases),
    expectedFiles: unique(expectedFiles),
    keywords,
  }
}

export const KEYWORD_TONES = {
  indigo: "border-indigo-200 bg-indigo-50 text-indigo-700",
  violet: "border-violet-200 bg-violet-50 text-violet-700",
  sky: "border-sky-200 bg-sky-50 text-sky-700",
  rose: "border-rose-200 bg-rose-50 text-rose-700",
  amber: "border-amber-200 bg-amber-50 text-amber-700",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
  slate: "border-slate-200 bg-slate-50 text-slate-700",
}
