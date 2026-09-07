import unittest
from reference_kernel.elmos_ai_factory.store_semantics_v4 import *
class T(unittest.TestCase):
 def test_records(self): self.assertTrue(records_equivalent([{'id':1}],[{'id':1}],'id'))
 def test_record_diff(self): self.assertFalse(records_equivalent([{'id':1}],[{'id':2}],'id'))
 def test_delete(self): self.assertTrue(deletion_complete(set(),set(),set(),set(),'x'))
 def test_vector(self): self.assertTrue(vector_migration_pass(.9,.89,100,110))
 def test_cdc(self): self.assertTrue(cdc_ready(0,0,2,5))
