import { writeFile } from "node:fs/promises";

export async function writeDemoReport(input) {
  const html = renderDemoReport(input);
  await writeFile(input.outPath, html, "utf8");
  return html;
}

export function renderDemoReport(input) {
  const run = input.run ?? {};
  const steps = Array.isArray(run.steps) ? run.steps : [];
  const toolNames = steps
    .map((step) => step?.tool_call?.name)
    .filter((name) => typeof name === "string");
  const replayMiss = input.replayMissProof?.replayMiss ?? {};

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Datalox FlowCyto Visible Replay Demo</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f4;
      --ink: #1e2528;
      --muted: #637074;
      --line: #d9ded9;
      --panel: #ffffff;
      --accent: #126c5f;
      --accent-soft: #e2f0ec;
      --warn-soft: #fff4d8;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
    }
    main {
      max-width: 1120px;
      margin: 0 auto;
      padding: 40px 24px 56px;
    }
    header {
      display: grid;
      gap: 10px;
      margin-bottom: 28px;
    }
    h1 {
      margin: 0;
      font-size: 32px;
      line-height: 1.15;
      letter-spacing: 0;
    }
    h2 {
      margin: 0 0 12px;
      font-size: 18px;
      letter-spacing: 0;
    }
    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }
    a {
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin: 22px 0;
    }
    .card, .section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }
    .card strong {
      display: block;
      margin-bottom: 8px;
      font-size: 15px;
    }
    .status {
      display: inline-block;
      border-radius: 999px;
      padding: 3px 9px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 10px;
    }
    .warn {
      background: var(--warn-soft);
      color: #745400;
    }
    .section {
      margin-top: 18px;
    }
    ol {
      margin: 0;
      padding-left: 22px;
    }
    li {
      margin: 10px 0;
      line-height: 1.5;
    }
    code, pre {
      font-family: var(--mono);
      font-size: 13px;
    }
    pre {
      overflow: auto;
      background: #101516;
      color: #eef4f2;
      border-radius: 8px;
      padding: 14px;
    }
    .artifact-list {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .artifact-list a {
      font-family: var(--mono);
      font-size: 13px;
    }
  </style>
</head>
<body>
  <main>
    <header>
      <span class="status">visible local proof</span>
      <h1>FlowCyto Gating QC Replay Demo</h1>
      <p>This report was generated from local demo artifacts. It proves the fixture set can be installed, a model can run through replayed FlowCyto tools, live/API drift is rejected by replay miss behavior, and one SFT frame can be exported.</p>
    </header>

    <section class="grid" aria-label="proof cards">
      ${proofCard("Fixture Installed", input.fixtureSetRef, [
        ["installed", input.installResult?.installed ?? input.installResult?.status ?? "recorded"],
        ["ref", input.installResult?.ref ?? input.fixtureSetRef],
      ])}
      ${proofCard("Agent Used FlowCyto Tools", `${toolNames.length} tool steps`, [
        ["tool path", toolNames.join(" -> ")],
        ["stop reason", input.runResult?.stopReason ?? run.stop_reason],
      ])}
      ${proofCard("Replay World Only", replayMiss.code ?? "replay_miss", [
        ["tool", replayMiss.tool_name],
        ["liveFallback", replayMiss.liveFallback],
      ], "warn")}
      ${proofCard("Run Artifact", input.artifactPaths?.runPath ?? "run/run.json", [
        ["schema", run.schema_version],
        ["fixture set", run.fixture_set_ref],
      ])}
      ${proofCard("SFT Export", `${input.exportResult?.frameCount ?? 0} frame`, [
        ["path", input.artifactPaths?.sftPath],
        ["quality", "derived from replay evidence"],
      ])}
    </section>

    <section class="section">
      <h2>Tool Timeline</h2>
      <ol>
        ${steps.map(renderStep).join("\n        ")}
      </ol>
    </section>

    <section class="section">
      <h2>Replay Miss Proof</h2>
      <p>The demo intentionally calls a known FlowCyto tool with unrecorded arguments after the run. The replay runtime returns a structured miss and does not fall back to live tools.</p>
      <pre>${escapeHtml(JSON.stringify(input.replayMissProof, null, 2))}</pre>
    </section>

    <section class="section">
      <h2>Artifacts</h2>
      <div class="artifact-list">
        ${artifactLink("Run Artifact", input.artifactPaths?.runPath)}
        ${artifactLink("Transcript JSONL", input.artifactPaths?.transcriptPath)}
        ${artifactLink("SFT Export", input.artifactPaths?.sftPath)}
        ${artifactLink("Replay Miss Proof", input.artifactPaths?.replayMissPath)}
        ${artifactLink("Terminal Log", input.artifactPaths?.terminalLogPath)}
      </div>
    </section>

    <section class="section">
      <h2>Final Answer</h2>
      <pre>${escapeHtml(run.final_answer ?? "")}</pre>
    </section>
  </main>
</body>
</html>
`;
}

function proofCard(title, value, rows, tone = "") {
  return `<article class="card">
        <strong>${escapeHtml(title)}</strong>
        <span class="status ${tone}">${escapeHtml(String(value ?? ""))}</span>
        ${rows.map(([key, rowValue]) => `<p><code>${escapeHtml(key)}</code>: ${escapeHtml(String(rowValue ?? ""))}</p>`).join("\n        ")}
      </article>`;
}

function renderStep(step) {
  const toolCall = step?.tool_call;
  if (!toolCall) {
    return `<li><strong>assistant</strong>: ${escapeHtml(step?.assistant_message?.content ?? "final response")}</li>`;
  }
  const status = step?.observation?.status ?? "unknown";
  return `<li><strong>${escapeHtml(toolCall.name)}</strong> <code>${escapeHtml(status)}</code><br><code>${escapeHtml(JSON.stringify(toolCall.arguments))}</code></li>`;
}

function artifactLink(label, href) {
  if (typeof href !== "string" || href.length === 0) {
    return "";
  }
  return `<a href="${escapeAttribute(href)}">${escapeHtml(label)}: ${escapeHtml(href)}</a>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("\"", "&quot;");
}
