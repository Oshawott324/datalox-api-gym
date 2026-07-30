version 1.0

task exit_nonzero {
  command <<<
    printf '%s\n' 'intentional failure on stderr' >&2
    exit 23
  >>>

  output {
    String unreachable = read_string(stdout())
  }
}

workflow failure_case {
  call exit_nonzero
}
