export type EnforcementLevel = "enforced" | "conditional" | "guidance_only";

export type HostSurfaceId =
  | "codex"
  | "claude"
  | "generic_cli"
  | "mcp_only"
  | "repo_instructions";

export interface HostCapability {
  id: HostSurfaceId;
  enforcementLevel: EnforcementLevel;
  supportsPreRunInjection: boolean;
  supportsPostRunHook: boolean;
  supportsSecondPassReview: boolean;
  requiresPromptPlaceholder: boolean;
  description: string;
}

export const HOST_CAPABILITIES: Record<HostSurfaceId, HostCapability> = {
  codex: {
    id: "codex",
    enforcementLevel: "enforced",
    supportsPreRunInjection: true,
    supportsPostRunHook: false,
    supportsSecondPassReview: true,
    requiresPromptPlaceholder: false,
    description: "Codex shim intercepts exec/e/review and routes runs through the Datalox wrapper.",
  },
  claude: {
    id: "claude",
    enforcementLevel: "enforced",
    supportsPreRunInjection: true,
    supportsPostRunHook: true,
    supportsSecondPassReview: true,
    requiresPromptPlaceholder: false,
    description: "Claude shim can enforce pre-run prompt injection; Stop hooks are post-turn sidecars, while native skills and MCP remain model-chosen guidance surfaces.",
  },
  generic_cli: {
    id: "generic_cli",
    enforcementLevel: "conditional",
    supportsPreRunInjection: true,
    supportsPostRunHook: false,
    supportsSecondPassReview: false,
    requiresPromptPlaceholder: true,
    description: "Generic CLI wrapper is only enforced when the host exposes a prompt placeholder.",
  },
  mcp_only: {
    id: "mcp_only",
    enforcementLevel: "guidance_only",
    supportsPreRunInjection: false,
    supportsPostRunHook: false,
    supportsSecondPassReview: false,
    requiresPromptPlaceholder: false,
    description: "MCP tools are available, but the model still chooses whether to call them.",
  },
  repo_instructions: {
    id: "repo_instructions",
    enforcementLevel: "guidance_only",
    supportsPreRunInjection: false,
    supportsPostRunHook: false,
    supportsSecondPassReview: false,
    requiresPromptPlaceholder: false,
    description: "Repo instruction files influence behavior, but they do not enforce loop boundaries.",
  },
};

export function listHostCapabilities(): HostCapability[] {
  return Object.values(HOST_CAPABILITIES);
}

export function getHostCapability(id: HostSurfaceId): HostCapability {
  return HOST_CAPABILITIES[id];
}
