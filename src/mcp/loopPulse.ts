import { access } from "node:fs/promises";
import path from "node:path";

export interface LoopPulse {
  command: string;
  repo_path: string | null;
  has_agent_wiki: boolean;
  has_install_stamp: boolean;
  has_hot_cache: boolean;
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

function deriveLoopHint(command: string, result: unknown, state: {
  hasAgentWiki: boolean;
  hasInstallStamp: boolean;
}): Pick<LoopPulse, "recommended_next_tool" | "action_hint"> {
  if (!state.hasAgentWiki) {
    return {
      recommended_next_tool: "adopt_pack",
      action_hint: "Repo-local Datalox surfaces are missing; adopt or bootstrap the repo before relying on pack state.",
    };
    }

    switch (command) {
    case "resolve_loop": {
      const typed = result as { matches?: unknown[]; directNoteMatches?: unknown[] } | null;
      const hasMatches = (typed?.matches?.length ?? 0) > 0 || (typed?.directNoteMatches?.length ?? 0) > 0;
      return hasMatches
        ? {
            recommended_next_tool: "record_turn_result",
            action_hint: "Guidance matched for this loop. Apply it, then record grounded outcomes if the turn produced reusable evidence.",
          }
        : {
            recommended_next_tool: "record_turn_result",
            action_hint: "No skill or supporting note matched. If the turn uncovers a reusable gap, record it so it can accumulate evidence into a note or skill.",
          };
    }
    case "record_turn_result": {
      const occurrenceCount = Number((result as { occurrenceCount?: unknown } | null)?.occurrenceCount ?? 0);
      return occurrenceCount > 1
        ? {
            recommended_next_tool: "promote_gap",
            action_hint: `This grounded signal has repeated ${occurrenceCount} times. Promote it if it is now reusable beyond the current turn.`,
          }
        : {
            recommended_next_tool: "resolve_loop",
            action_hint: "First grounded occurrence recorded. Promote only after the same signal repeats with strong evidence.",
          };
    }
    case "record_trajectory":
      return {
        recommended_next_tool: "grade_trajectories",
        action_hint: "Trajectory row recorded. Grade training readiness before buyer-facing export.",
      };
    case "grade_trajectories":
      return {
        recommended_next_tool: "repair_trajectory",
        action_hint: "Trajectory grading completed. Repair rows with blocking diagnostics, or export curated rows with a quality filter when ready.",
      };
    case "repair_trajectory":
      return {
        recommended_next_tool: "grade_trajectories",
        action_hint: "Corrected trajectory row recorded as a new event. Grade the repaired row before export.",
      };
    case "export_trajectories":
      return {
        recommended_next_tool: null,
        action_hint: "Trajectory export completed. Review blocked or rejected rows before sharing the JSONL corpus.",
      };
    case "patch_knowledge":
      return {
        recommended_next_tool: "lint_pack",
        action_hint: "Knowledge changed. Lint the pack before relying on the new note or skill.",
      };
    case "promote_gap": {
      const action = (result as { decision?: { action?: unknown } } | null)?.decision?.action;
      return {
        recommended_next_tool: "lint_pack",
        action_hint: typeof action === "string"
          ? `Promotion decision: ${action}. Lint after the change so the visible artifacts stay coherent.`
          : "Promotion evaluated. Lint after any note or skill changes.",
      };
    }
    case "lint_pack":
      return (result as { ok?: unknown } | null)?.ok === false
        ? {
            recommended_next_tool: null,
            action_hint: "Lint found issues. Inspect agent-wiki/lint.md and fix the pack state before continuing.",
          }
        : {
            recommended_next_tool: null,
            action_hint: "Pack lint is clean.",
          };
    case "capture_web_artifact":
    case "capture_design_source":
    case "capture_pdf_artifact":
      return {
        recommended_next_tool: "lint_pack",
        action_hint: "Capture wrote repo-local evidence. Promote it into durable knowledge only after later trace evidence proves reuse.",
      };
    case "publish_web_capture":
      return {
        recommended_next_tool: null,
        action_hint: "Published capture artifacts. Validate the generated manifest and public index outputs.",
      };
    case "adopt_pack":
      return {
        recommended_next_tool: state.hasInstallStamp ? "resolve_loop" : null,
        action_hint: "Pack files were copied into the repo. Resolve the next loop from the host repo or install host support if needed.",
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
  const hasAgentWiki = repoPath ? await exists(path.join(repoPath, "agent-wiki")) : false;
  const hasInstallStamp = repoPath ? await exists(path.join(repoPath, ".datalox", "install.json")) : false;
  const hasHotCache = repoPath ? await exists(path.join(repoPath, "agent-wiki", "hot.md")) : false;
  const hint = deriveLoopHint(input.command, input.result, {
    hasAgentWiki,
    hasInstallStamp,
  });
  const unavailableTools = new Set(input.options?.unavailableTools ?? []);
  const recommendedNextTool = hint.recommended_next_tool && unavailableTools.has(hint.recommended_next_tool)
    ? input.options?.fallbackRecommendedTool ?? null
    : hint.recommended_next_tool;

  return {
    command: input.command,
    repo_path: repoPath,
    has_agent_wiki: hasAgentWiki,
    has_install_stamp: hasInstallStamp,
    has_hot_cache: hasHotCache,
    recommended_next_tool: recommendedNextTool,
    action_hint: hint.action_hint,
  };
}
