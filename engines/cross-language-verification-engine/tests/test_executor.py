from elmos_cross_language_verification.executor import ExecutorRegistry
from elmos_cross_language_verification.models import Language

def test_executor_registry():
    exec_py = ExecutorRegistry.get_executor(Language.PYTHON)
    assert exec_py is not None
    res = exec_py.execute("print(1)", {"a": 1})
    assert res.success is True
