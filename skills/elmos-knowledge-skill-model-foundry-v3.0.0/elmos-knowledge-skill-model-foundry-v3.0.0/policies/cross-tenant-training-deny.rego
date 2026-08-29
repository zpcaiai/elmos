package elmos.cross_tenant_training

default allow := false

allow if {
  input.dataset_tier == "Gold"
  input.explicit_tenant_opt_in
  input.training_scope == "tenant-adapter"
  input.eval_leakage_free
  input.rights_verified
}
