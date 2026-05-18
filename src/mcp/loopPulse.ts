import { access } from "node:fs/promises";
import path from "node:path";

export interface LoopPulse {
  command: string;
  repo_path: string | null;
  has_install_stamp: boolean;
  recommended_next_tool: string | null;
  action_hint: string;
}

export interface LoopPulseOptions {
  unavailableTools?: readonly string[];
  fallbackRecommendedTool?: string | null;
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function deriveLoopHint(command: string): Pick<LoopPulse, "recommended_next_tool" | "action_hint"> {
  switch (command) {
    case "adopt_pack":
      return {
        recommended_next_tool: null,
        action_hint: "Product surfaces were copied into the repo. Record source replay data under .datalox/tool-io, .datalox/events/agent-turns, and .datalox/replay-bundles.",
      };
    default:
      return {
        recommended_next_tool: null,
        action_hint: "Command completed.",
      };
  }
}

export async function buildLoopPulse(input: {
  command: string;
  repoPath?: string;
  result: unknown;
  options?: LoopPulseOptions;
}): Promise<LoopPulse> {
  const repoPath = input.repoPath ? path.resolve(input.repoPath) : null;
  const hasInstallStamp = repoPath ? await exists(path.join(repoPath, ".datalox", "install.json")) : false;
  const hint = deriveLoopHint(input.command);
  const unavailableTools = new Set(input.options?.unavailableTools ?? []);
  const recommendedNextTool = hint.recommended_next_tool && unavailableTools.has(hint.recommended_next_tool)
    ? input.options?.fallbackRecommendedTool ?? null
    : hint.recommended_next_tool;

  return {
    command: input.command,
    repo_path: repoPath,
    has_install_stamp: hasInstallStamp,
    recommended_next_tool: recommendedNextTool,
    action_hint: hint.action_hint,
  };
}
