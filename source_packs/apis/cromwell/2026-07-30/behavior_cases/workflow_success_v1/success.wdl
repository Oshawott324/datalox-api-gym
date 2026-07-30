version 1.0

task write_message {
  input {
    String message
  }

  command <<<
    printf '%s\n' '~{message}' > result.txt
  >>>

  output {
    File result_file = "result.txt"
    String echoed = read_string("result.txt")
  }
}

workflow success_case {
  input {
    String message
  }

  call write_message {
    input:
      message = message
  }

  output {
    File result_file = write_message.result_file
    String echoed = write_message.echoed
  }
}
