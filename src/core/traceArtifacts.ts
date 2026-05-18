import type { SourceBundle } from "./sourceBundle.js";

export interface RenderTraceNoteInput {
  bundle: SourceBundle;
  workflow: string;
  notePath?: string;
  related?: string[];
  sources?: string[];
}

export interface RenderSkillFromTraceInput {
  id: string;
  name: string;
  description: string;
  workflow: string;
  trigger: string;
  notePaths: string[];
  maturity?: "draft" | "stable";
  evidenceCount?: number;
  lastUsedAt?: string;
}

function list(items: string[], fallback: string): string[] {
  if (items.length === 0) {
    return [`- ${fallback}`];
  }
  return items.map((item) => `- ${item}`);
}

function sectionText(bundle: SourceBundle, title: string): string | null {
  return bundle.structure.sections.find((section) => section.title === title)?.text?.trim() ?? null;
}

function firstMeaningfulHeading(bundle: SourceBundle): string | null {
  return bundle.structure.headings.find((heading) => !heading.startsWith("Workflow:") && !heading.startsWith("Matched Skill:")) ?? null;
}

export function renderTraceNote(input: RenderTraceNoteInput): string {
  const title = input.bundle.source.title;
  const signal = input.bundle.evidence.textSnippets[0] ?? "Trace evidence recorded for this loop.";
  const task = sectionText(input.bundle, "Task");
  const summary = sectionText(input.bundle, "Summary");
  const interpretation = firstMeaningfulHeading(input.bundle)
    ?? summary
    ?? "This trace captured reusable loop evidence.";
  const action = input.bundle.evidence.textSnippets[2]
    ?? "Check this note before repeating the same loop.";
  const whenToUse = task
    ? `Use this note when ${task.toLowerCase()} and the same signal shows up again.`
    : `Use this note when ${signal.charAt(0).toLowerCase()}${signal.slice(1)} reappears.`;

  return [
    "---",
    "type: note",
    "kind: trace",
    `title: ${title}`,
    `workflow: ${input.workflow}`,
    "status: active",
    input.related && input.related.length > 0 ? "related:" : "related: []",
    ...(input.related && input.related.length > 0 ? input.related.map((item) => `  - ${item}`) : []),
    input.sources && input.sources.length > 0 ? "sources:" : "sources: []",
    ...(input.sources && input.sources.length > 0 ? input.sources.map((item) => `  - ${item}`) : []),
    `updated: ${input.bundle.source.capturedAt}`,
    "---",
    "",
    `# ${title}`,
    "",
    "## When to Use",
    "",
    whenToUse,
    "",
    "## Signal",
    "",
    signal,
    "",
    "## Interpretation",
    "",
    interpretation,
    "",
    "## Action",
    "",
    action,
    "",
    "## Examples",
    "",
    ...list(input.bundle.evidence.textSnippets.slice(0, 5), "Add a concrete trace excerpt here."),
    "",
    "## Evidence",
    "",
    ...(input.notePath ? [`- Note path: ${input.notePath}`] : []),
    `- Captured at: ${input.bundle.source.capturedAt}`,
    ...list(
      input.bundle.structure.sections.map((section) => `${section.title}: ${section.text}`),
      "Add a concrete trace section here.",
    ),
    "",
    "## Related",
    "",
    ...list(input.related ?? [], "Add a related note or skill here."),
    "",
  ].join("\n");
}

export function renderSkillFromTrace(input: RenderSkillFromTraceInput): string {
  const updatedAt = input.lastUsedAt ?? new Date().toISOString();

  return [
    "---",
    `name: ${input.name}`,
    `description: ${input.description}`,
    "metadata:",
    "  datalox:",
    `    id: ${input.id}`,
    `    workflow: ${input.workflow}`,
    `    trigger: ${input.trigger}`,
    "    note_paths:",
    ...input.notePaths.map((notePath) => `      - ${notePath}`),
    `    maturity: ${input.maturity ?? "draft"}`,
    `    evidence_count: ${input.evidenceCount ?? 1}`,
    `    updated_at: ${updatedAt}`,
    "---",
    "",
    `# ${input.name}`,
    "",
    "## When to Use",
    "",
    input.trigger,
    "",
    "## Workflow",
    "",
    "1. Read the linked notes.",
    "2. Follow the recurring procedure captured by those notes.",
    "3. Return the decision, action, and evidence used.",
    "",
    "## Expected Output",
    "",
    "- why this skill matched",
    "- what action was taken",
    "- which notes justified the action",
    "",
    "## Notes",
    "",
    ...input.notePaths.map((notePath) => `- ${notePath}`),
    "",
  ].join("\n");
}
