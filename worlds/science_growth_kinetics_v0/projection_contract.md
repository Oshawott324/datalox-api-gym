# Projection Contract

The world executes PyLabRobot 0.2.1 OT-2 simulator calls for every liquid transfer and Chatterbox calls for incubator loading/release and plate-reader absorbance. These calls establish interface execution and tracker behavior, not hardware fidelity.

The 30 C, 600 nm, 200 uL, eight-replicate, two-minute, 20-hour values are selected from the retained Agilent application note. The inclusive schedule contains 601 observations. The blank well, ten-minute preconditioning interval, deterministic logistic values, reader-busy timing, partial-run fault, and revision-bump timing are benchmark-defined. They are workflow fixtures, not biological or production-frequency claims.

The complete deterministic OD600 series remains in authoritative world state for verification. Agent readback returns a bounded per-well summary and SHA-256 digest so a 5,409-value payload does not dominate model context.

Plate transport between independent fixtures is state-projected; no robot arm is executed. Live hardware and network calls are inexpressible.
