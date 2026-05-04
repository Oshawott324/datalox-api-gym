import process from "node:process";

import { runSharedMcpServer } from "./sharedServer.js";
import { getSharedMcpCommands } from "../surface/sharedCommands.js";

async function main(): Promise<void> {
  await runSharedMcpServer({
    name: "datalox-pack-mcp",
    version: "0.1.0",
    commands: getSharedMcpCommands(),
  });
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exit(1);
});
