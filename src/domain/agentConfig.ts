export const PACK_MODES = [
  "repo_only",
  "service_backed",
] as const;

export type PackMode = (typeof PACK_MODES)[number];

export const AGENT_PROFILES = [
  "local_first",
  "runtime_first",
] as const;

export type AgentProfile = (typeof AGENT_PROFILES)[number];

export const AGENT_INTERFACES = [
  "skill_loop",
  "runtime_compile",
] as const;

export type AgentInterface = (typeof AGENT_INTERFACES)[number];

export const SOURCE_KINDS = [
  "local_repo",
  "runtime_retrieval",
] as const;

export type SourceKind = (typeof SOURCE_KINDS)[number];

export interface MaintenanceBacklogThreshold {
  uncovered?: number;
  oldestAgeDays?: number;
  maintainableGroups?: number;
}

export interface MaintenanceConfig {
  maxEvents: number;
  minNoteOccurrences: number;
  minSkillOccurrences: number;
  automatic: {
    enabled: boolean;
    write: boolean;
    lockStaleMs: number;
  };
  backlog: {
    warn: MaintenanceBacklogThreshold;
    urgent: MaintenanceBacklogThreshold;
  };
}

export const DEFAULT_MAINTENANCE_CONFIG: MaintenanceConfig = {
  maxEvents: 12,
  minNoteOccurrences: 2,
  minSkillOccurrences: 3,
  automatic: {
    enabled: true,
    write: true,
    lockStaleMs: 5 * 60 * 1000,
  },
  backlog: {
    warn: {
      uncovered: 50,
      oldestAgeDays: 7,
      maintainableGroups: 1,
    },
    urgent: {
      uncovered: 100,
      oldestAgeDays: 14,
      maintainableGroups: 5,
    },
  },
};

export interface AgentConfig {
  version: number;
  mode: PackMode;
  project: {
    id: string;
    name: string;
  };
  sources: Array<{
    kind: SourceKind;
    name: string;
    enabled: boolean;
    root: string;
  }>;
  agent: {
    profile: AgentProfile;
    nativeSkillPolicy: "preserve";
    detectOnEveryLoop: boolean;
    configReadOrder: string[];
    interfaceOrder: AgentInterface[];
  };
  paths: {
    seedSkillsDir: string;
    seedNotesDir: string;
    hostSkillsDir: string | null;
    hostNotesDir: string | null;
    seedPatternsDir?: string | null;
    hostPatternsDir?: string | null;
  };
  maintenance: MaintenanceConfig;
  runtime: {
    enabled: boolean;
    baseUrl: string;
    defaultWorkflow: string;
    requestTimeoutMs: number;
    endpoints: {
      compile: string;
      guidance: string;
      publish: string;
      search: string;
      install: string;
      ingest: string;
      register: string;
    };
  };
  auth: {
    apiKeyEnv: string;
    contributorKeyEnv: string;
  };
}
