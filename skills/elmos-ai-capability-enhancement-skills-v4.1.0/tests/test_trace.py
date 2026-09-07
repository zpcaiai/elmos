import unittest
from reference_kernel.elmos_ai_factory.trace import validate_trace, compare_traces

def event(i, typ, key, status="OK", causes=None):
    return {"id":f"e{i}","type":typ,"sequence":i,"payloadHash":str(i%10)*64,
            "semanticKey":key,"status":status,"causes":causes or []}

class TraceTests(unittest.TestCase):
    def test_valid_trace(self):
        trace={"events":[event(0,"input","q"),event(1,"terminal","done","COMPLETED",["e0"])]}
        self.assertEqual([], validate_trace(trace))

    def test_unknown_cause_is_invalid(self):
        trace={"events":[event(0,"terminal","done","COMPLETED",["missing"])]}
        self.assertTrue(any("unknown causal" in e for e in validate_trace(trace)))

    def test_equivalent_framework_traces(self):
        ref={"events":[event(0,"input","q"),event(1,"retrieval","docs"),event(2,"terminal","done","COMPLETED")]}
        cand={"events":[event(0,"input","q"),event(1,"retrieval","docs"),event(2,"terminal","done","COMPLETED")]}
        self.assertTrue(compare_traces(ref,cand)["equivalent"])

    def test_side_effect_order_mismatch(self):
        ref={"events":[event(0,"side-effect","write-a"),event(1,"side-effect","write-b"),event(2,"terminal","done","COMPLETED")]}
        cand={"events":[event(0,"side-effect","write-b"),event(1,"side-effect","write-a"),event(2,"terminal","done","COMPLETED")]}
        result=compare_traces(ref,cand)
        self.assertFalse(result["equivalent"])
        self.assertTrue(any(m["kind"]=="side-effect-order" for m in result["mismatches"]))
