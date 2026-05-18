import {
  buildLoopEnvelope,
  captureReplayEvidenceSnapshot,
  finalizeWrappedRun,
  hasExplicitPromptPlaceholder,
  runWrappedCommand,
  sanitizeWrappedCommandResult,
  type LoopEnvelopeInput,
  type LoopEnvelope,
  type WrapperMatchRunner,
  type WrapperReviewRunner,
  type WrapperPostRunInput,
} from "../shared.js";

export interface ClaudeWrapperInput extends LoopEnvelopeInput, WrapperPostRunInput {
  claudeBin?: string;
  claudeArgs?: string[];
  reviewModel?: string;
}

const CLAUDE_OPTIONS_WITH_VALUES = new Set([
  "-r",
  "--resume",
  "--model",
  "--permission-mode",
  "--allowedTools",
  "--disallowedTools",
  "--mcp-config",
  "--append-system-prompt",
  "--system-prompt",
  "--output-format",
  "--input-format",
  "--cwd",
]);

const CLAUDE_NO_VALUE_FLAGS = new Set([
  "-p",
  "--print",
  "-c",
  "--continue",
]);

const CLAUDE_PASSTHROUGH_COMMANDS = new Set([
  "mcp",
  "update",
  "config",
]);

function findClaudePromptIndex(args: string[]): number {
  if (args.length === 0) {
    return -1;
  }

  const first = args[0];
  if (CLAUDE_PASSTHROUGH_COMMANDS.has(first)) {
    return -1;
  }

  let promptIndex = -1;
  let skipNext = false;
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (skipNext) {
      skipNext = false;
      continue;
    }
    if (arg === "--") {
      break;
    }
    if (arg.startsWith("--") && arg.includes("=")) {
      continue;
    }
    if (CLAUDE_OPTIONS_WITH_VALUES.has(arg)) {
      skipNext = true;
      continue;
    }
    if (CLAUDE_NO_VALUE_FLAGS.has(arg)) {
      continue;
    }
    if (arg.startsWith("-")) {
      continue;
    }
    promptIndex = index;
  }

  return promptIndex;
}

function inferPromptFromClaudeArgs(args: string[]): string | undefined {
  const promptIndex = findClaudePromptIndex(args);
  return promptIndex === -1 ? undefined : args[promptIndex];
}

function buildClaudeReviewer(
  claudeBin: string,
  reviewModel: string | undefined,
): WrapperReviewRunner {
  return {
    kind: "claude",
    model: reviewModel ?? null,
    run(prompt: string, envelope: LoopEnvelope) {
      const reviewArgs = [
        ...(reviewModel ? ["--model", reviewModel] : []),
        "--print",
        prompt,
      ];
      return runWrappedCommand(claudeBin, reviewArgs, envelope, {
        cwd: envelope.repoPath,
        hostKind: "claude",
        env: {
          DATALOX_REVIEW_PASS: "1",
        },
      });
    },
  };
}

function buildClaudeMatcher(
  claudeBin: string,
  matchModel: string,
): WrapperMatchRunner {
  return {
    kind: "claude",
    model: matchModel,
    run(prompt: string, envelope: LoopEnvelope) {
      const matchArgs = [
        "--model",
        matchModel,
        "--print",
        prompt,
      ];
      return runWrappedCommand(claudeBin, matchArgs, envelope, {
        cwd: envelope.repoPath,
        hostKind: "claude",
        env: {
          DATALOX_MATCH_PASS: "1",
        },
      });
    },
  };
}

export async function runClaudeWrapper(input: ClaudeWrapperInput) {
  const claudeBin = input.claudeBin ?? process.env.DATALOX_CLAUDE_BIN ?? "claude";
  const matchModel = process.env.DATALOX_MATCH_MODEL ?? input.reviewModel ?? "gpt-5.4-mini";
  const claudeArgs = input.claudeArgs && input.claudeArgs.length > 0
    ? [...input.claudeArgs]
    : [];
  const inferredPrompt = input.prompt ?? inferPromptFromClaudeArgs(claudeArgs) ?? input.task;
  const envelope = await buildLoopEnvelope({
    ...input,
    prompt: inferredPrompt,
    matcher: buildClaudeMatcher(claudeBin, matchModel),
  });

  const promptIndex = findClaudePromptIndex(claudeArgs);
  const isPassThroughCommand = claudeArgs.length > 0 && CLAUDE_PASSTHROUGH_COMMANDS.has(claudeArgs[0]);
  let finalArgs: string[];
  if (claudeArgs.some((arg) => hasExplicitPromptPlaceholder(arg))) {
    finalArgs = claudeArgs;
  } else if (promptIndex !== -1) {
    finalArgs = [...claudeArgs];
    finalArgs[promptIndex] = envelope.wrappedPrompt;
  } else if (isPassThroughCommand) {
    finalArgs = [...claudeArgs];
  } else {
    finalArgs = [...claudeArgs, envelope.wrappedPrompt];
  }

  const replayEvidenceBefore = await captureReplayEvidenceSnapshot(envelope.repoPath);
  const executed = runWrappedCommand(claudeBin, finalArgs, envelope, {
    cwd: envelope.repoPath,
    hostKind: "claude",
  });
  const sanitized = sanitizeWrappedCommandResult(executed);

  return {
    envelope,
    child: sanitized.child,
    postRun: await finalizeWrappedRun(envelope, executed, {
      hostKind: "claude",
      task: input.task,
      workflow: input.workflow,
      step: input.step,
      skillId: input.skillId ?? input.skill,
      summary: input.summary,
      tags: input.tags,
      eventKind: input.eventKind,
      postRunMode: input.postRunMode,
      replayEvidenceBefore,
      minWikiOccurrences: input.minWikiOccurrences,
      minSkillOccurrences: input.minSkillOccurrences,
      reviewModel: input.reviewModel,
      reviewer: buildClaudeReviewer(claudeBin, input.reviewModel),
    }),
  };
}
