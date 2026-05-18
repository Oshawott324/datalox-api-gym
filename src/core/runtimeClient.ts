// Thin HTTP client for the Datalox runtime service.
// Talks to the retrieval/registry/compiler APIs.

import type { AgentConfig } from "../domain/agentConfig.js";

// Shared runtime types (kept minimal to avoid cross-repo imports)

export interface DocRef {
  type: "file" | "url" | "registry";
  ref: string;
  label?: string;
}

export interface SkillSearchQuery {
  query?: string;
  workflow?: string;
  tags?: string[];
  source?: string;
  limit?: number;
}

export interface SkillSearchHit {
  skill: RemoteRegistrySkill;
  score: number;
}

export interface RemoteRegistrySkill {
  id: string;
  name: string;
  displayName: string;
  description: string;
  workflow: string;
  trigger: string;
  version: string;
  skillMd: string;
  source: string;
  status: string;
  tags: string[];
  downloads: number;
  docRefs: DocRef[];
  defaultDocRef?: DocRef;
  contributorKey: string;
  createdAt: string;
  updatedAt: string;
}

export interface SkillInstallBundle {
  name: string;
  version: string;
  skillMd: string;
  docRefs: DocRef[];
  metadata: {
    displayName: string;
    description: string;
    source: string;
    tags: string[];
    contributor: string;
    downloads: number;
    createdAt: string;
    updatedAt: string;
  };
}

export interface PublishSkillInput {
  name: string;
  displayName?: string;
  description: string;
  workflow: string;
  trigger?: string;
  version?: string;
  skillMd: string;
  source?: string;
  status?: string;
  tags?: string[];
  docRefs?: DocRef[];
  defaultDocRef?: DocRef;
}

export interface CompileGuidanceRequest {
  task: string;
  workflow: string;
  step?: string;
  observations?: string[];
  tags?: string[];
  limit?: number;
  maxSnippets?: number;
}

export interface RuntimeGuidance {
  task: string;
  workflow: string;
  step?: string;
  skill: {
    id: string;
    name: string;
    displayName: string;
    workflow: string;
    trigger: string;
    docRefs: DocRef[];
    defaultDocRef?: DocRef;
    tags: string[];
    status: string;
  } | null;
  docs: Array<{
    fileId: string;
    title: string;
    workflow: string;
    tags: string[];
    score: number;
    preview: string;
    fromSkill?: string;
  }>;
  snippets: Array<{
    fileId: string;
    title: string;
    snippet: string;
    matches: string[];
    score: number;
  }>;
  citations: Array<{
    fileId: string;
    title: string;
    checksum: string;
  }>;
  nextReads: string[];
  escalationRequired: boolean;
  escalationReason?: string;
  summary: string;
}

export interface IngestFileInput {
  fileName: string;
  title?: string;
  workflow: string;
  content: string;
  contentType?: string;
  tags?: string[];
  metadata?: Record<string, string>;
}

export interface RegisterContributorInput {
  email: string;
  displayName?: string;
}

export interface ContributorKey {
  key: string;
  email: string;
  displayName: string;
  totalContributions: number;
  createdAt: string;
}

type RuntimeEndpoints = AgentConfig["runtime"]["endpoints"];

export class RuntimeClient {
  private readonly baseUrl: string;
  private readonly endpoints: RuntimeEndpoints;
  private readonly timeoutMs: number;
  private readonly contributorKey: string | undefined;

  constructor(
    runtimeConfig: AgentConfig["runtime"],
    contributorKey?: string,
  ) {
    this.baseUrl = runtimeConfig.baseUrl.replace(/\/+$/, "");
    this.endpoints = runtimeConfig.endpoints;
    this.timeoutMs = runtimeConfig.requestTimeoutMs;
    this.contributorKey = contributorKey;
  }

  // Skill discovery

  async searchSkills(query: SkillSearchQuery): Promise<SkillSearchHit[]> {
    const url = this.url(this.endpoints.search);
    const response = await this.post<{ hits: SkillSearchHit[] }>(url, query);
    return response.hits ?? [];
  }

  async installSkill(name: string): Promise<SkillInstallBundle | null> {
    const endpoint = this.endpoints.install.replace(":name", encodeURIComponent(name));
    const url = this.url(endpoint);
    const response = await this.get<{ bundle: SkillInstallBundle | null }>(url);
    return response.bundle ?? null;
  }

  // Guidance (skill-aware retrieval)

  async compileGuidance(request: CompileGuidanceRequest): Promise<RuntimeGuidance> {
    const url = this.url(this.endpoints.guidance);
    const response = await this.post<{ guidance: RuntimeGuidance }>(url, request);
    return response.guidance;
  }

  // Contributing back

  async publishSkill(
    input: PublishSkillInput,
  ): Promise<{ skill: RemoteRegistrySkill; validationErrors?: unknown[] }> {
    const url = this.url(this.endpoints.publish);
    return this.post(url, input, true);
  }

  async registerContributor(input: RegisterContributorInput): Promise<ContributorKey> {
    const url = this.url(this.endpoints.register);
    const response = await this.post<{ contributor: ContributorKey }>(url, input);
    return response.contributor;
  }

  // Doc ingestion

  async ingestFile(input: IngestFileInput): Promise<{ file: unknown }> {
    const url = this.url(this.endpoints.ingest);
    return this.post(url, input);
  }

  // Internals

  private url(endpoint: string): string {
    return `${this.baseUrl}${endpoint}`;
  }

  private async post<T>(url: string, body: unknown, auth = false): Promise<T> {
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (auth && this.contributorKey) {
      headers["authorization"] = `Bearer ${this.contributorKey}`;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`Runtime POST ${url} failed (${response.status}): ${text}`);
      }
      return (await response.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  private async get<T>(url: string): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`Runtime GET ${url} failed (${response.status}): ${text}`);
      }
      return (await response.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }
}

// Factory: create a client from config, returns null if runtime is disabled
export function createRuntimeClient(
  config: AgentConfig,
  contributorKey?: string,
): RuntimeClient | null {
  if (!config.runtime.enabled) return null;
  const key = contributorKey ?? (config.auth.contributorKeyEnv
    ? process.env[config.auth.contributorKeyEnv]
    : undefined);
  return new RuntimeClient(config.runtime, key);
}
