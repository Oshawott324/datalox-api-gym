export type SourceKind = "trace" | "web" | "pdf";

export interface SourceBundleSection {
  title: string;
  text: string;
}

export interface SourceBundleCitation {
  label: string;
  target?: string;
}

export interface SourceBundleStyle {
  fonts: string[];
  fontSizes: string[];
  fontWeights: string[];
  colors: string[];
  backgrounds: string[];
  borderRadii: string[];
  shadows: string[];
  transitions: string[];
  cssVariables: Array<{ name: string; value: string }>;
}

export interface SourceBundle {
  kind: SourceKind;
  source: {
    id: string;
    title: string;
    capturedAt: string;
    url?: string;
    path?: string;
  };
  structure: {
    headings: string[];
    sections: SourceBundleSection[];
  };
  evidence: {
    textSnippets: string[];
    links?: string[];
    screenshots?: string[];
    citations?: SourceBundleCitation[];
  };
  style?: SourceBundleStyle;
}

export interface PageSnapshot {
  title: string;
  url: string;
  metaDescription: string | null;
  lang: string | null;
  navItems: string[];
  headings: string[];
  buttons: string[];
  sections: Array<{ tag: string; label: string; text: string }>;
  fonts: string[];
  fontSizes: string[];
  fontWeights: string[];
  colors: string[];
  backgrounds: string[];
  borderRadii: string[];
  shadows: string[];
  transitions: string[];
  cssVariables: Array<{ name: string; value: string }>;
  forms: number;
  inputs: number;
  links: number;
}

export interface ExtractTraceSourceInput {
  id: string;
  title: string;
  capturedAt: string;
  task?: string;
  workflow?: string;
  step?: string;
  transcript?: string;
  summary?: string;
  observations?: string[];
  signal?: string;
  interpretation?: string;
  action?: string;
  matchedSkillId?: string;
  changedFiles?: string[];
  outcome?: string;
}

export interface ExtractWebSourceInput {
  id: string;
  title: string;
  capturedAt: string;
  url: string;
  desktop: PageSnapshot;
  mobile: PageSnapshot;
  screenshots?: string[];
}

export interface ExtractPdfSourceInput {
  id: string;
  title: string;
  capturedAt: string;
  path: string;
  url?: string;
  pageCount: number;
  pages: Array<{ number: number; text: string }>;
  citations?: SourceBundleCitation[];
}

function unique(items: Array<string | null | undefined>): string[] {
  return [...new Set(items.map((item) => item?.trim() ?? "").filter(Boolean))];
}

function compactText(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function compactLines(value: string | null | undefined): string[] {
  return unique(
    (value ?? "")
      .split(/\r?\n/)
      .map((line) => compactText(line))
      .filter(Boolean),
  );
}

export function extractTraceSource(input: ExtractTraceSourceInput): SourceBundle {
  const sections: SourceBundleSection[] = [];
  if (input.task?.trim()) {
    sections.push({ title: "Task", text: input.task.trim() });
  }
  if (input.summary?.trim()) {
    sections.push({ title: "Summary", text: input.summary.trim() });
  }
  if (input.transcript?.trim()) {
    sections.push({ title: "Transcript", text: input.transcript.trim() });
  }
  if (input.changedFiles && input.changedFiles.length > 0) {
    sections.push({ title: "Changed Files", text: input.changedFiles.join("\n") });
  }

  const headings = unique([
    input.workflow ? `Workflow: ${input.workflow}` : null,
    input.step ? `Step: ${input.step}` : null,
    input.matchedSkillId ? `Matched Skill: ${input.matchedSkillId}` : null,
    input.outcome ? `Outcome: ${input.outcome}` : null,
  ]);

  const textSnippets = unique([
    ...(input.observations ?? []),
    input.signal,
    input.interpretation,
    input.action,
    input.summary,
    input.outcome,
  ]);

  return {
    kind: "trace",
    source: {
      id: input.id,
      title: input.title,
      capturedAt: input.capturedAt,
    },
    structure: {
      headings,
      sections,
    },
    evidence: {
      textSnippets,
      links: input.changedFiles?.length ? [...input.changedFiles] : undefined,
    },
  };
}

export function extractWebSource(input: ExtractWebSourceInput): SourceBundle {
  const sections = input.desktop.sections.map((section) => ({
    title: section.label || section.tag,
    text: compactText(section.text),
  }));

  return {
    kind: "web",
    source: {
      id: input.id,
      title: input.title,
      capturedAt: input.capturedAt,
      url: input.url,
    },
    structure: {
      headings: unique(input.desktop.headings),
      sections,
    },
    evidence: {
      textSnippets: unique([
        input.desktop.metaDescription,
        ...input.desktop.navItems,
        ...input.desktop.buttons,
        ...input.desktop.sections.map((section) => section.text),
        ...input.mobile.buttons,
      ]),
      links: unique([input.url]),
      screenshots: input.screenshots?.length ? [...input.screenshots] : undefined,
    },
    style: {
      fonts: unique(input.desktop.fonts),
      fontSizes: unique(input.desktop.fontSizes),
      fontWeights: unique(input.desktop.fontWeights),
      colors: unique(input.desktop.colors),
      backgrounds: unique(input.desktop.backgrounds),
      borderRadii: unique(input.desktop.borderRadii),
      shadows: unique(input.desktop.shadows),
      transitions: unique(input.desktop.transitions),
      cssVariables: input.desktop.cssVariables
        .map((item) => ({ name: item.name.trim(), value: item.value.trim() }))
        .filter((item) => item.name && item.value),
    },
  };
}

export function extractPdfSource(input: ExtractPdfSourceInput): SourceBundle {
  const sections = input.pages
    .map((page) => ({
      title: `Page ${page.number}`,
      text: compactText(page.text),
    }))
    .filter((page) => page.text);

  const headings = unique(
    input.pages
      .flatMap((page) => compactLines(page.text).slice(0, 1))
      .slice(0, 12),
  );

  return {
    kind: "pdf",
    source: {
      id: input.id,
      title: input.title,
      capturedAt: input.capturedAt,
      url: input.url,
      path: input.path,
    },
    structure: {
      headings,
      sections,
    },
    evidence: {
      textSnippets: unique(
        input.pages.flatMap((page) => compactLines(page.text).slice(0, 4)),
      ),
      links: input.url ? [input.url] : undefined,
      citations: input.citations?.length ? [...input.citations] : undefined,
    },
  };
}
