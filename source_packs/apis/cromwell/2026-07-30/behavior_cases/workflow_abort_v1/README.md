# Cromwell 92 Workflow ABORT Behavior V1

This immutable case is one exact program captured from a fresh disposable
Cromwell 92 server using the Local backend and a file-backed HSQLDB database.
It submits a long-running workflow, polls through observed transient `404` and
`Submitted` responses until exactly `Running`, aborts it, repeats the exact
abort request, exercises the provider-native `404` for an unknown all-zero
workflow UUID, and polls through observed `Running` and `Aborting` states until
exactly `Aborted`. It then captures empty outputs, returned log paths, and final
metadata with an observed running-to-aborted relation of `changed`.

The offline target is an exact captured-program projection. It is not an
implementation of arbitrary Cromwell workflow behavior. Production and reset
equivalence are not claimed. Returned log paths are retained as JSON evidence;
the referenced files are not dereferenced.
