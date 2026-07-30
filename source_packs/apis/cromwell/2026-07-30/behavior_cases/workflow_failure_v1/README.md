# Cromwell 92 Workflow FAILURE Behavior V1

This immutable case is one exact program captured from a fresh disposable
Cromwell 92 server using the Local backend and a file-backed HSQLDB database.
It covers a service-before read, byte-identical non-idempotent valid workflow
submissions, bounded primary and duplicate polling through transient states to
`Failed`, empty primary outputs, primary log paths, and the provider-native
`404` returned when aborting the already terminal failed primary workflow.
Final metadata retains the exact Local task failure with return code `23`,
`retryableFailure=false`, and a submitted-to-failed relation of `changed`.

The offline target is an exact captured-program projection. It is not an
implementation of arbitrary Cromwell workflow behavior. Production and reset
equivalence are not claimed. Returned log paths are retained as JSON evidence;
the referenced files are not dereferenced.
