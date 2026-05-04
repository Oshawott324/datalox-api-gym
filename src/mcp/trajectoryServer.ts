import process from "node:process";

import { runSharedMcpServer } from "./sharedServer.js";
import { getSharedMcpCommands } from "../surface/sharedCommands.js";

const TRAJECTORY_MCP_TOOL_NAMES = new Set([
  "record_trajectory",
  "export_trajectories",
]);

async function main(): Promise<void> {
  const commands = getSharedMcpCommands().filter((command) => TRAJECTORY_MCP_TOOL_NAMES.has(command.mcpTool));
  await runSharedMcpServer({
    name: "datalox-trajectory-mcp",
    version: "0.1.0",
    commands,
    unavailableLoopPulseTools: [
      "adopt_pack",
      "resolve_loop",
      "record_turn_result",
      "patch_knowledge",
      "promote_gap",
      "maintain_knowledge",
      "lint_pack",
      "capture_web_artifact",
      "capture_design_source",
      "capture_pdf_artifact",
      "publish_web_capture",
    ],
    fallbackLoopPulseTool: null,
  });
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exit(1);
});
