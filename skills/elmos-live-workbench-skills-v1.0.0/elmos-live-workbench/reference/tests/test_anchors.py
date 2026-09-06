import tempfile, unittest
from pathlib import Path
from lw_core.anchors import *

class AnchorTests(unittest.TestCase):
    def test_unicode_roundtrip(self):
        data="a中😀z\r\n第二行\n".encode()
        for line,col in [(0,0),(0,1),(0,2),(0,4),(0,5),(1,0),(1,3),(2,0)]:
            with self.subTest(line=line,col=col):
                self.assertEqual(byte_to_lsp_utf16(data,lsp_utf16_to_byte(data,line,col)),(line,col))
    def test_surrogate_half_rejected(self):
        with self.assertRaises(ValueError):lsp_utf16_to_byte("😀".encode(),0,1)
    def test_byte_inside_unicode_rejected(self):
        with self.assertRaises(UnicodeDecodeError):byte_to_lsp_utf16("中".encode(),1)
    def test_empty_selection_inside_unicode_rejected(self):
        d="中".encode()
        with self.assertRaises(UnicodeDecodeError):extract(d,digest(d),1,1)
    def test_crlf_interior_rejected(self):
        with self.assertRaises(ValueError):byte_to_lsp_utf16(b"a\r\nb",2)
    def test_lsp_column_cannot_include_crlf(self):
        with self.assertRaises(ValueError):lsp_utf16_to_byte(b"a\r\nb",0,2)
    def test_empty_file(self):
        self.assertEqual(lsp_utf16_to_byte(b"",0,0),0)
    def test_bom_preserved(self):
        d="\ufeff中".encode()
        self.assertEqual(lsp_utf16_to_byte(d,0,1),3)
        self.assertEqual(extract(d,digest(d),0,3),"\ufeff")
    def test_stale_digest(self):
        with self.assertRaises(ValueError):extract(b"new",digest(b"old"),0,1)
    def test_bad_ranges(self):
        for a,b in [(-1,1),(2,1),(0,99)]:
            with self.subTest(a=a,b=b), self.assertRaises(ValueError):extract(b"ok",digest(b"ok"),a,b)
    def test_bad_paths(self):
        for p in ["/etc/passwd","../a","a/../b","a//b","a/./b","a\\b","x\x00","", "a/"]:
            with self.subTest(p=p),self.assertRaises(ValueError):validate_path(p)
    def test_safe_read(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'x.py').write_text('ok')
            self.assertEqual(read_snapshot_file(Path(d),'x.py'),b'ok')
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'x').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):read_snapshot_file(Path(d),'x')
