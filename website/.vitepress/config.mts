import { defineConfig } from "vitepress";

export default defineConfig({
  title: "Datalox API Gym",
  description: "Agentic worlds for training and evaluating tool-using agents.",
  themeConfig: {
    nav: [
      { text: "Guide", link: "/guide/quickstart" },
      { text: "Worlds", link: "/worlds/billing-support-v0" },
      { text: "Benchmarks", link: "/benchmarks" }
    ],
    sidebar: [
      {
        text: "Guide",
        items: [
          { text: "Quickstart", link: "/guide/quickstart" }
        ]
      },
      {
        text: "Concepts",
        items: [
          { text: "Agentic World Contract", link: "/concepts/agentic-world-contract" }
        ]
      },
      {
        text: "Worlds",
        items: [
          { text: "Billing Support v0", link: "/worlds/billing-support-v0" },
          { text: "UniteLabs Plate QC v0", link: "/worlds/unitelabs-plate-qc-v0" }
        ]
      },
      {
        text: "Benchmarks",
        items: [
          { text: "Benchmarks", link: "/benchmarks" }
        ]
      }
    ]
  }
});
