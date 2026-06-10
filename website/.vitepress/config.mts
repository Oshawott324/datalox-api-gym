import { defineConfig } from "vitepress";

export default defineConfig({
  title: "Datalox API Gym",
  description: "Resettable fake APIs for training and evaluating tool-using agents.",
  themeConfig: {
    nav: [
      { text: "Guide", link: "/guide/quickstart" },
      { text: "Worlds", link: "/worlds/billing-support-v0" },
      { text: "Demos", link: "/demos/unitelabs-chat-demo" },
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
          { text: "Stateful Fake APIs", link: "/concepts/stateful-fake-apis" }
        ]
      },
      {
        text: "Worlds",
        items: [
          { text: "Billing Support v0", link: "/worlds/billing-support-v0" }
        ]
      },
      {
        text: "Demos",
        items: [
          { text: "UniteLabs Chat Demo", link: "/demos/unitelabs-chat-demo" }
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
