version 1.0

task wait_long_enough_to_abort {
  command <<<
    printf '%s\n' 'started'
    sleep 120
    printf '%s\n' 'finished' > result.txt
  >>>

  output {
    File result_file = "result.txt"
  }
}

workflow abort_case {
  call wait_long_enough_to_abort
}
