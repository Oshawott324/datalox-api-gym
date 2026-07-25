# Synergy H1 Yeast Growth v0

`synergy_h1_yeast_growth_v0` is one SQLite, logical-time-only dry-run world for
`yeast_growth_20h_kinetic`. It models assignment of a sealed 96-well plate and
collection of eight 200 uL dilution replicates at 30 C and 600 nm every two
minutes for 20 hours. The inclusive schedule (`t=0` and `t=20h`) is a
benchmark-defined 601 observations.

## Grounding boundary

- Backend-grounded tools project locally inspected PyLabRobot 0.2.1
  `SynergyH1Backend` methods. They never invoke that backend or hardware.
- `reader_load_plate` projects PLR `ResourceHolder` child-resource assignment,
  which the PLR documentation requires before close.
- `advance_logical_time` and `submit_growth_decision` are benchmark-local.
- The app note specifies continuous orbital shaking at 559 CPM and 1 mm.
  PLR 0.2.1 exposes only `shake(shake_type, frequency)`, where its source
  comment maps device setting 3 to 567 CPM. Executable v0 therefore uses
  `ORBITAL` plus setting 3 as `assumption_for_calibration`. It does not expose
  or verify exact 1 mm amplitude and makes no claim that 567 CPM equals 559 CPM.
- The temperature ramp and absorbance values are deterministic calibration
  assumptions. They are not biological predictions or claims.

Run package admission:

```bash
python -c "from pathlib import Path; from api_gym.worlds.synergy_h1_yeast_growth_v0.admission import run_admission_checks; print(run_admission_checks(out_dir=Path('/tmp/synergy-admission'))['ok'])"
```

Sources and exact locators are in `source_refs.json`; modeled and omitted
semantics are in `projection_contract.md`.
