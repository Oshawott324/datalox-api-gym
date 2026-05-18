export interface PdfSectionSpan {
  title: string;
  startPage: number;
  endPage: number;
  summary: string;
}

export interface PdfNormalizedPage {
  page: number;
  section: string;
  text: string;
}

export interface PdfEvidenceBundle {
  headings: string[];
  sections: Array<{ title: string; text: string }>;
  textSnippets: string[];
  sectionMap: PdfSectionSpan[];
  pages: PdfNormalizedPage[];
}

interface WorkingPage {
  page: number;
  section: string;
  text: string;
  sentences: string[];
}

const CONTROL_TEXT_PATTERN = /[\u0000-\u001F\u007F]/g;
const WHITESPACE_PATTERN = /\s+/g;

const FULL_TEXT_REMOVALS: RegExp[] = [
  /As a library, NLM provides access to scientific literature\.\s*/gi,
  /Inclusion in an NLM database does not imply endorsement of, or agreement with, the contents by NLM or the National Institutes of Health\.\s*/gi,
  /Learn more:\s*PMC Disclaimer\s*\|\s*PMC Copyright Notice\s*/gi,
  /Articles from .*? are provided here courtesy of .*$/gim,
];

const LINE_DROP_PATTERNS: RegExp[] = [
  /^author information$/i,
  /^article notes$/i,
  /^copyright and license information$/i,
  /^pmcid:\s*/i,
  /^pmid:\s*/i,
  /^\[doi.*$/i,
  /^\[pubmed.*$/i,
  /^\[google scholar.*$/i,
  /^associated data$/i,
];

const SECTION_MATCHERS: Array<{ title: string; pattern: RegExp }> = [
  { title: "Supplementary Materials", pattern: /\b(?:supplementary materials?|appendix|supplementary methods?|supplementary figures?|supplementary tables?)\b/i },
  { title: "Methods", pattern: /\b(?:materials and methods|methods|experimental procedures?|method details?)\b/i },
  { title: "Results and Discussion", pattern: /\bresults and discussion\b/i },
  { title: "Results", pattern: /\bresults\b/i },
  { title: "Discussion", pattern: /\bdiscussion\b/i },
  { title: "Conclusion", pattern: /\bconclusions?\b/i },
  { title: "Abstract", pattern: /\babstract\b/i },
  { title: "Introduction", pattern: /\bintroduction\b/i },
  { title: "Figure Legends", pattern: /\b(?:figure legends?|fig\.?\s*s?\d+)\b/i },
  { title: "Tables", pattern: /\btable\s*s?\d+\b/i },
  { title: "Data Availability", pattern: /\bdata availability\b/i },
  { title: "References", pattern: /\breferences\b/i },
  { title: "Acknowledgments", pattern: /\backnowledg(?:e)?ments?\b/i },
];

function compactText(value: string | null | undefined): string {
  return (value ?? "").replace(WHITESPACE_PATTERN, " ").trim();
}

function unique(items: string[]): string[] {
  return [...new Set(items.map((item) => item.trim()).filter(Boolean))];
}

function normalizePdfText(value: string): string {
  let normalized = value.replace(CONTROL_TEXT_PATTERN, " ");
  normalized = normalized.replace(/([A-Za-z])-\s+([A-Za-z])/g, "$1$2");
  for (const pattern of FULL_TEXT_REMOVALS) {
    normalized = normalized.replace(pattern, " ");
  }
  const lines = normalized
    .split(/\r?\n/)
    .map((line) => compactText(line))
    .filter(Boolean)
    .filter((line) => !LINE_DROP_PATTERNS.some((pattern) => pattern.test(line)));
  return compactText(lines.join(" "));
}

function splitSentences(value: string): string[] {
  return value
    .split(/(?<=[.!?])\s+(?=[A-Z0-9])/)
    .map((sentence) => compactText(sentence))
    .filter((sentence) => sentence.length >= 20);
}

function detectSection(text: string, previousSection: string | null): string {
  const earlyWindow = text.slice(0, 1500);
  for (const matcher of SECTION_MATCHERS) {
    if (matcher.pattern.test(earlyWindow)) {
      return matcher.title;
    }
  }
  return previousSection ?? "Document";
}

function isReferenceLike(sentence: string): boolean {
  return /\bet al\.\b/i.test(sentence)
    || /\b(?:pmid|doi)\b/i.test(sentence)
    || /\b(?:vol\.|pp\.|proc\.|journal|pubmed|google scholar)\b/i.test(sentence);
}

function buildSectionMap(pages: WorkingPage[]): PdfSectionSpan[] {
  const spans: PdfSectionSpan[] = [];
  for (const page of pages) {
    const summary = page.sentences.find((sentence) => !isReferenceLike(sentence)) ?? page.text.slice(0, 240);
    const previous = spans[spans.length - 1];
    if (previous && previous.title === page.section) {
      previous.endPage = page.page;
      if (!previous.summary && summary) {
        previous.summary = summary;
      }
      continue;
    }
    spans.push({
      title: page.section,
      startPage: page.page,
      endPage: page.page,
      summary,
    });
  }
  return spans;
}

function buildHeadings(sectionMap: PdfSectionSpan[]): string[] {
  return unique(sectionMap.map((section) => section.title)).slice(0, 12);
}

function buildTextSnippets(pages: WorkingPage[]): string[] {
  const snippets: string[] = [];
  for (const preferredSection of ["Abstract", "Methods", "Supplementary Materials", "Results", "Discussion", "Document"]) {
    for (const page of pages) {
      if (page.section !== preferredSection) {
        continue;
      }
      for (const sentence of page.sentences) {
        if (isReferenceLike(sentence)) {
          continue;
        }
        snippets.push(sentence);
        if (snippets.length >= 8) {
          return unique(snippets);
        }
      }
    }
  }
  return unique(snippets);
}

function buildSections(sectionMap: PdfSectionSpan[]): Array<{ title: string; text: string }> {
  return sectionMap.map((section) => ({
    title: section.startPage === section.endPage
      ? `${section.title} (page ${section.startPage})`
      : `${section.title} (pages ${section.startPage}-${section.endPage})`,
    text: section.summary,
  }));
}

export function extractPdfEvidence(input: {
  pageCount: number;
  pages: Array<{ number: number; text: string }>;
}): PdfEvidenceBundle {
  let currentSection: string | null = null;
  const pages: WorkingPage[] = input.pages
    .map((page) => {
      const normalizedText = normalizePdfText(page.text);
      if (!normalizedText) {
        return null;
      }
      currentSection = detectSection(normalizedText, currentSection);
      return {
        page: page.number,
        section: currentSection,
        text: normalizedText,
        sentences: splitSentences(normalizedText),
      };
    })
    .filter((page): page is WorkingPage => page !== null);

  const sectionMap = buildSectionMap(pages);

  return {
    headings: buildHeadings(sectionMap),
    sections: buildSections(sectionMap),
    textSnippets: buildTextSnippets(pages),
    sectionMap,
    pages: pages.map((page) => ({
      page: page.page,
      section: page.section,
      text: page.text,
    })),
  };
}
