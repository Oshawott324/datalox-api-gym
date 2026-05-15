import process from "node:process";

import { runSharedMcpServer } from "./sharedServer.js";
import { getSharedMcpCommands } from "../surface/sharedCommands.js";

const TRAJECTORY_MCP_TOOL_NAMES = new Set([
  "record_trajectory",
  "export_trajectories",
  "record_agent_task_trajectory",
  "export_agent_task_trajectories",
  "grade_trajectories",
  "repair_trajectory",
]);

async function main(): Promise<void> {
  const commands = getSharedMcpCommands().filter((command) => TRAJECTORY_MCP_TOOL_NAMES.has(command.mcpTool));
  await runSharedMcpServer({
    name: "datalox-trajectory-mcp",
    version: "0.1.0",
    commands,
    unavailableLoopPulseTools: ["adopt_pack"],
    fallbackLoopPulseTool: null,
  });
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exit(1);
});
