from elmos_spring_modernization.transaction_boundary import TransactionBoundaryExtractor

def test_extract_tx():
    extractor = TransactionBoundaryExtractor()
    config = extractor.extract([{"name": "saveUser", "propagation": "REQUIRES_NEW"}])
    assert "saveUser" in config.method_policies
    assert config.method_policies["saveUser"].propagation == "REQUIRES_NEW"

def test_extract_too_many():
    extractor = TransactionBoundaryExtractor()
    try:
        extractor.extract([{"name": f"method{i}"} for i in range(501)])
        assert False
    except ValueError:
        assert True

def test_propagation_chains_and_self_invocation():
    extractor = TransactionBoundaryExtractor()
    methods = [
        {
            "name": "com.example.OrderService.createOrder",
            "propagation": "REQUIRED",
            "isolation": "READ_COMMITTED",
            "calls": ["com.example.OrderService.validateOrder", "com.example.BillingService.charge"]
        },
        {
            "name": "com.example.OrderService.validateOrder",
            "propagation": "REQUIRES_NEW",
            "calls": []
        },
        {
            "name": "com.example.BillingService.charge",
            "propagation": "REQUIRES_NEW",
            "calls": ["com.example.AuditService.log"]
        },
        {
            "name": "com.example.AuditService.log",
            "propagation": "NOT_SUPPORTED",
            "calls": []
        }
    ]
    config = extractor.extract(methods)
    assert len(config.method_policies) == 4

    # Verify propagation chains were computed
    assert len(config.propagation_chains) >= 1
    # Check that BillingService.charge -> AuditService.log chain exists
    chain_strs = [" -> ".join(chain) for chain in config.propagation_chains]
    assert any("OrderService.createOrder" in c and "BillingService.charge" in c for c in chain_strs)

    # Verify self-invocation anti-pattern was caught: OrderService.createOrder calls OrderService.validateOrder
    assert any("Self-invocation proxy bypass detected" in ap for ap in config.anti_patterns)

def test_propagation_conflict_detection():
    extractor = TransactionBoundaryExtractor()
    methods = [
        {
            "name": "com.example.ServiceA.doTx",
            "propagation": "REQUIRED",
            "calls": ["com.example.ServiceB.doNever"]
        },
        {
            "name": "com.example.ServiceB.doNever",
            "propagation": "NEVER",
            "calls": []
        }
    ]
    config = extractor.extract(methods)
    assert any("Transaction propagation conflict" in ap and "NEVER" in ap for ap in config.anti_patterns)
