# OT-2 Motion v0 Runtime Bundle

This bundle projects one existing API Gym OT-2 motion task through the
`datalox-gated-runtime` `WorldImplementationV1` and MCP machinery. The runtime
owns one persistent native Opentrons 9.1.1 simulator worker per active episode.

The admitted episode is `engineering_control_02`: move from the declared slot 1
start to slot 3 well A1, 5 mm above the top. The collision model is an authored
0.5 mm sphere and thin wall. It is not pipette, tip, labware, deck, or physical
robot geometry, and it has not been validated on a robot.

Agent tools are limited to setup inspection, well and deck-point movement,
requesting a declared operator observation, and explicit deferral. This first
episode does not authorize labware-offset edits, so no offset mutation tool is
exposed. The trusted controller must select the native interpreter through
`DATALOX_OT2_WORKER_PYTHON`; no tool argument can select an interpreter, file,
import, URL, hardware address, or authorization flag.

Managed-worker sessions are create-only. Reset discards the worker generation
and creates a fresh one. Resume from the SQLite session is rejected by the
runtime because native simulator state is not restorable.
