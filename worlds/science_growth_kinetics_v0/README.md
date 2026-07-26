# Science Growth Kinetics v0

A resettable cross-service science-agent world over eLabFTW-shaped records and executed PyLabRobot 0.2.1 simulator/Chatterbox mechanisms. Twelve episodes cover nominal execution, resource recovery, reader availability, partial-run recovery, and protocol freshness. No hardware or network execution is available.

Build and check:

```bash
python scripts/worlds/build_science_growth_kinetics.py
python scripts/worlds/build_science_growth_kinetics.py --check
datalox-gate env admit-world --env worlds/science_growth_kinetics_v0 --json
```
