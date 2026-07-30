# Cromwell 92 Workflow SUCCESS Behavior V1

This immutable case is one exact program captured from a fresh disposable
Cromwell 92 server using the Local backend and a file-backed HSQLDB database.
It covers a service read, byte-identical non-idempotent workflow submissions,
the provider-native missing-source rejection, bounded primary and duplicate
polling, primary outputs and logs, and final successful metadata.
The final metadata keeps exact `Succeeded` evidence and records the observed
workflow status relation from submitted to succeeded as `changed`.

The offline target is an exact captured-program projection. It is not an
implementation of arbitrary Cromwell workflow behavior. Production and reset
equivalence are not claimed. Returned log paths are retained as JSON evidence;
the referenced files are not dereferenced.
