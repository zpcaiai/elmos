package elmos.formal.solver_execution_test
import rego.v1
import data.elmos.formal.solver_execution

test_unpinned_prod_image_is_denied if {
  result := solver_execution.deny with input as {
    "environment":"PROD",
    "adapter":{"spec":{"execution":{"image":"latest"},"security":{"network":"deny","secrets":"none","runAsNonRoot":true,"readOnlyRootFilesystem":true}}}
  }
  count(result) == 1
}
