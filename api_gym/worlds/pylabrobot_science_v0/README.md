# PyLabRobot Science Workflows v0

This world contains three visually and scientifically distinct dry-run workflow
families:

1. `qpcr_amplification_qc`: heated-lid motion, a 42-cycle-stage/82-step thermal
   program, cycle progression, and a control-aware qPCR result artifact.
2. `incubator_growth_campaign`: eight storage slots, a temperature ramp,
   orbital-shaking exposure, accelerated logical time, and OD600 measurements
   from a separate plate-reader surface at 0/2/4/6/8 hours.
3. `gravimetric_powder_formulation`: vial custody across a powder dispenser and
   analytical balance, coarse and correction pulses, and a measured target
   tolerance.

The world uses installed PyLabRobot 0.2.1 front-end contracts for thermocycler,
incubator, plate-reader, powder-dispenser, and scale operations. It does not
connect to hardware.

## Grounding Boundary

The following are PyLabRobot-shaped operations:

- thermocycler lid, heated-lid, status, and `run_protocol` calls;
- incubator temperature, shaking, plate storage, and retrieval calls;
- plate-reader absorbance calls;
- powder-dispenser `dispense` calls;
- scale `tare` and `get_weight` calls.

The following are declared benchmark projections, not vendor claims:

- accelerated logical time and temperature ramp rates;
- qPCR fluorescence and Ct artifacts;
- microbial growth-shaped OD600 values;
- powder delivery error and balance noise;
- physical transfer duration between stations.

This distinction is encoded in each scenario contract and in returned artifact
metadata. A richer visualization must not be interpreted as a hardware-fidelity
simulator.

## Run

```bash
api-gym session create \
  --world pylabrobot_science_v0 \
  --scenario qpcr_amplification_qc \
  --seed 1 \
  --out runs/qpcr
```

Available scenarios:

```text
qpcr_amplification_qc
incubator_growth_campaign
gravimetric_powder_formulation
```

## Export A Visualization

```bash
python -m api_gym.worlds.pylabrobot_science_v0.visualization \
  --scenario incubator_growth_campaign \
  --out runs/incubator-growth-visualization.json
```

The output is a portable `datalox_visualization_run_v1` document accepted by
the visualization service in `datalox-gated-runtime`. The thermocycler,
incubator-shaker, and powder-balance scenes use separate validated renderer
variants rather than a liquid-handler deck with changed labels.
