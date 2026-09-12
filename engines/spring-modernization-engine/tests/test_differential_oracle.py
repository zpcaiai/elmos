from elmos_spring_modernization.differential_oracle import DifferentialOracle

def test_configure():
    oracle = DifferentialOracle()
    config = oracle.configure("cmd1", "cmd2")
    assert config.source_port == 8080
