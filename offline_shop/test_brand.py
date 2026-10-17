import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app

class BrandTests(unittest.TestCase):
    def test_embedded_icon_is_multiresolution_and_materializes_without_extra_packages(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(app,'DATA',Path(tmp)):
            folder=app.materialize_brand()
            icon=(folder/'family-shop-v1.ico').read_bytes()
            reserved,kind,count=struct.unpack_from('<HHH',icon)
            self.assertEqual((reserved,kind),(0,1))
            sizes=set()
            for index in range(count):
                w,h,_,_,_,_,length,offset=struct.unpack_from('<BBBBHHII',icon,6+index*16)
                sizes.add((w or 256,h or 256))
                self.assertLessEqual(offset+length,len(icon))
                self.assertTrue(icon[offset:offset+length].startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertTrue({(16,16),(32,32),(48,48),(256,256)}.issubset(sizes))
            self.assertTrue((folder/'family-shop-v1.png').read_bytes().startswith(b'\x89PNG'))
            old=(folder/'family-shop-v1.ico').stat().st_mtime_ns
            app.materialize_brand()
            self.assertEqual((folder/'family-shop-v1.ico').stat().st_mtime_ns,old)

if __name__=='__main__':unittest.main()
