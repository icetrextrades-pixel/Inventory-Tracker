import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from ledger import Cloud,Ledger

class CloudTests(unittest.TestCase):
    def client(self):
        c=Cloud('https://example.supabase.co','sb_publishable_test');c.owner='00000000-0000-0000-0000-000000000001';return c
    def test_reject_insecure_host_and_privileged_key(self):
        for url,key in [('http://example.supabase.co','sb_publishable_test'),('https://example.supabase.co.attacker.com','sb_publishable_test'),('https://example.supabase.co','sb_secret_test')]:
            with self.assertRaises(ValueError):Cloud(url,key)
        token='eyJ.'+base64.urlsafe_b64encode(json.dumps({'role':'service_role'}).encode()).decode().rstrip('=')+'.sig'
        with self.assertRaises(ValueError):Cloud('https://example.supabase.co',token)
    def test_snapshot_round_trip_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'shop.sqlite3';l=Ledger(source);l.product('Bread','loaf');l.db.close()
            client=self.client();captured={}
            def request(path,payload=None):captured.update(payload);return 4
            client.request=request
            self.assertEqual(client.upload(source,3),4)
            self.assertEqual(captured['expected_version'],3)
            client.request=lambda path:[{'version':4,'payload':captured['snapshot']}]
            destination=Path(tmp)/'download.sqlite3'
            self.assertEqual(client.download(destination),4)
            self.assertEqual(destination.read_bytes(),source.read_bytes())
    def test_tampered_and_non_shop_backups_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=self.client();data=b'not a database'
            snapshot={'format':1,'sha256':'0'*64,'database':base64.b64encode(data).decode()}
            c.request=lambda path:[{'version':1,'payload':json.dumps(snapshot)}]
            with self.assertRaises(ValueError):c.download(Path(tmp)/'bad.sqlite3')
            snapshot['sha256']=hashlib.sha256(data).hexdigest()
            with self.assertRaises(ValueError):c.download(Path(tmp)/'bad.sqlite3')
    def test_conflict_surfaces_without_returning_sensitive_response(self):
        c=self.client()
        conflict=HTTPError(c.url,400,'Bad request',{},io.BytesIO(b'{"message":"CLOUD_CONFLICT"}'))
        with patch('urllib.request.urlopen',side_effect=conflict):
            with self.assertRaisesRegex(ValueError,'newer cloud copy'):c.request('/rest/v1/rpc/family_shop_upload',{})
        denied=HTTPError(c.url,401,'Denied',{},io.BytesIO(b'sensitive diagnostic'))
        with patch('urllib.request.urlopen',side_effect=denied):
            with self.assertRaisesRegex(ValueError,'HTTP 401') as error:c.request('/rest/v1/x')
        self.assertNotIn('sensitive diagnostic',str(error.exception))

if __name__=='__main__':unittest.main()
