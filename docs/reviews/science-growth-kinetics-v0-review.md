# Science Growth Kinetics v0: Domain Review

Date: 2026-07-26
Status: awaiting independent review

## Purpose

This review is limited to whether the scientific workflow, task assumptions,
and recovery decisions are plausible enough for a public agent benchmark. It
does not ask the reviewer to assess software architecture, model training,
reward design, or PyLabRobot implementation.

The world is a dry-run projection. PyLabRobot 0.2.1 methods execute against an
OT-2 simulator and incubator/plate-reader Chatterbox backends. No live
instrument, physical transport, sterility, measurement accuracy, or biological
prediction is claimed.

## Workflow Under Review

An agent must:

1. read the current protocol record;
2. inspect available liquid volumes and clean tips;
3. transfer 200 microliters into eight sample wells and one blank well, using
   one clean tip per transfer;
4. load the plate into a 30 C shaking incubation step;
5. wait for the declared stabilization interval before release;
6. start a 20-hour OD600 kinetic read at two-minute intervals;
7. reject partial or stale measurement series;
8. create and read back a result record containing the plate barcode, protocol
   revision, kinetic job ID, observation count, expected wells, and QC status.

The current fixture uses *Saccharomyces cerevisiae*, a 96-well plate, eight
sample replicates, one blank, 200 microliters per well, 30 C incubation, OD600,
a two-minute cadence, and a 20-hour duration. The inclusive schedule produces
601 observations.

## Recovery Cases

Please assess whether each expected agent response is scientifically and
operationally reasonable:

| Condition | Expected response |
| --- | --- |
| Primary source has insufficient volume | Use only the protocol-declared backup source; otherwise stop |
| Declared tip position is empty | Select another tracked clean tip; never reuse a used tip |
| Plate reader is busy | Wait or reschedule, then retry after availability |
| First kinetic read is partial | Do not document it as complete; run a complete replacement read |
| Protocol revision changes during the run | Re-read the protocol and reject results tied to the old revision |
| Result metadata references another plate or read job | Reject the result record |

## Questions

1. Is the overall sequence a plausible growth-kinetics workflow?
2. Which preparation, incubation, measurement, or record-keeping step is
   missing or materially wrong?
3. Are the controls and replicate assumptions sufficient for the narrow task,
   or should another control be required?
4. Is rerunning a partial kinetic read the right benchmark expectation? If not,
   what decision should depend on the failure timing and available data?
5. Is protocol-revision freshness a meaningful scientific or operational
   failure, and what evidence should establish that a result remains current?
6. Are any recovery cases unsafe, scientifically misleading, or too artificial
   to include?
7. Which values should be treated as protocol-specific variables rather than
   fixed benchmark invariants?
8. Which public protocol, instrument method, or paper should ground any
   correction?

## Review Record

Reviewer:

Affiliation or relevant experience:

Review date:

Disposition: `accept` / `accept_with_changes` / `reject`

Required changes:

Recommended changes:

Sources supplied by reviewer:

Permission to acknowledge reviewer publicly: `yes` / `no`
