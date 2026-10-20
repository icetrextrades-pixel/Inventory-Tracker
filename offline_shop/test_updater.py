import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import updater

class UpdateTests(unittest.TestCase):
    def test_pinned_download_and_hash_validation(self):
        content={name:(b'x=1\n' if name.endswith('.py') else b'test') for name in updater.FILES}
        tree={'tree':[{'path':'offline_shop/'+name,'type':'blob','size':len(data),'sha':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()} for name,data in content.items()]}
        urls=[]
        def fetch(url):
            urls.append(url)
            return json.dumps(tree).encode() if '/git/trees/' in url else content[url.rsplit('/',1)[1]]
        with tempfile.TemporaryDirectory() as tmp,patch.object(updater,'fetch',side_effect=fetch):
            updater.stage_update(Path(tmp),'a'*40)
            self.assertTrue((Path(tmp)/'app.py').exists())
            self.assertTrue(all('a'*40 in u for u in urls))
        tree['tree'][0]['sha']='0'*40
        with tempfile.TemporaryDirectory() as tmp,patch.object(updater,'fetch',side_effect=fetch):
            with self.assertRaises(ValueError):updater.stage_update(Path(tmp),'a'*40)

    def test_install_preserves_database_and_recovers_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stage=root/'stage';stage.mkdir();rollback=root/'recovery'
            for name in (*updater.FILES,'installed-version.txt'):
                (root/name).write_text('old');(stage/name).write_text('new')
            (root/'shop.sqlite3').write_bytes(b'private records')
            original=updater.os.replace
            def broken(source,target):
                if Path(target).name=='ledger.py':raise OSError('simulated write failure')
                return original(source,target)
            with patch.object(updater.os,'replace',side_effect=broken):
                with self.assertRaises(OSError):updater.install_staged(root,stage,rollback)
            self.assertEqual((root/'app.py').read_text(),'old')
            self.assertEqual((root/'shop.sqlite3').read_bytes(),b'private records')
            for name in (*updater.FILES,'installed-version.txt'):(stage/name).write_text('new')
            updater.install_staged(root,stage,rollback)
            self.assertEqual((root/'app.py').read_text(),'new')
            self.assertEqual((rollback/'app.py').read_text(),'old')
            self.assertEqual((root/'shop.sqlite3').read_bytes(),b'private records')

if __name__=='__main__':unittest.main()
