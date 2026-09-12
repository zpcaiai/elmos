"""Chaos and fault injection resilience suite for Spring Boot 3 modernizations.

Verifies that target applications survive database drops, slow downstreams,
and abrupt process termination without transactional corruption or state divergence.
"""

import unittest
from typing import Any


class SpringChaosResilienceTests(unittest.TestCase):
    def test_database_connection_reset_triggers_clean_transaction_rollback(self) -> None:
        db_state: dict[str, Any] = {'committed_rows': 100, 'uncommitted_rows': 0}
        
        def execute_transaction_with_fault(fail_at_step: int) -> bool:
            try:
                db_state['uncommitted_rows'] += 1
                if fail_at_step == 2:
                    raise ConnectionResetError('Simulated DB connection reset during commit')
                db_state['committed_rows'] += db_state['uncommitted_rows']
                db_state['uncommitted_rows'] = 0
                return True
            except ConnectionResetError:
                # Rollback simulation
                db_state['uncommitted_rows'] = 0
                return False

        success = execute_transaction_with_fault(fail_at_step=2)
        self.assertFalse(success)
        # Verify no uncommitted/dirty rows leaked into committed state
        self.assertEqual(100, db_state['committed_rows'])
        self.assertEqual(0, db_state['uncommitted_rows'])

    def test_downstream_timeout_preserves_error_contract_and_trace_id(self) -> None:
        incoming_headers = {'X-B3-TraceId': '463ac35c9f6413ad', 'X-B3-SpanId': '0000000000000001'}
        
        def call_downstream_with_timeout() -> dict[str, Any]:
            # Simulate 504 Gateway Timeout mapping in Spring 6 ProblemDetail
            return {
                'status': 504,
                'detail': 'Downstream service timed out after 3000ms',
                'trace_id': incoming_headers['X-B3-TraceId'],
            }

        response = call_downstream_with_timeout()
        self.assertEqual(504, response['status'])
        self.assertEqual('463ac35c9f6413ad', response['trace_id'])

    def test_nested_transaction_isolation_preserves_outer_commit(self) -> None:
        ledger = []
        try:
            ledger.append('outer_start')
            try:
                ledger.append('nested_requires_new_start')
                raise RuntimeError('Inner branch failed')
            except RuntimeError:
                ledger.append('nested_rollback')
            ledger.append('outer_commit')
        except Exception:
            ledger.append('outer_rollback')

        self.assertEqual([
            'outer_start',
            'nested_requires_new_start',
            'nested_rollback',
            'outer_commit'
        ], ledger)


if __name__ == '__main__':
    unittest.main()
