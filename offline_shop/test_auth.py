from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ledger import AuthStore,AuthSession,EmailRecovery,Ledger

PASSWORD='Private owner passphrase 8472'
NEW='Replacement owner passphrase 4926'

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'security'/'owner.sqlite3';self.store=AuthStore(self.path)
        self.key=self.store.setup('Osmando',PASSWORD,'A private phrase?','eight quiet bowls')
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def test_login_and_session_revocation(self):
        session=self.store.login('  OSMANDO  ',PASSWORD);self.assertTrue(session.valid())
        self.store.require(session);self.store.lock()
        self.assertFalse(session.valid())
        with self.assertRaises(PermissionError):self.store.require(session)
    def test_third_failure_logs_claimed_name_and_lockout_survives_restart(self):
        with patch('time.time',return_value=1000):
            for _ in range(3):
                with self.assertRaises(ValueError):self.store.login('Visitor','wrong password')
            alert=self.store.db.execute('SELECT * FROM attempts WHERE alert=1').fetchone()
            self.assertEqual(alert['name'],'Visitor')
            self.store.db.close();self.store=AuthStore(self.path)
            with self.assertRaisesRegex(ValueError,'Temporarily locked'):self.store.login('Osmando',PASSWORD)
        with patch('time.time',return_value=1061):self.assertTrue(self.store.login('Osmando',PASSWORD).valid())
    def test_global_limit_prevents_cycling_names(self):
        for name in ['A','B','C']:
            with self.assertRaises(ValueError):self.store.login(name,'incorrect')
        with self.assertRaisesRegex(ValueError,'Temporarily locked'):self.store.login('D','incorrect')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM attempts WHERE alert=1').fetchone()[0],1)
    def test_secrets_are_hashed_and_separate_from_shop_records(self):
        row=self.store.owner()
        self.assertNotIn(PASSWORD,row['password']);self.assertNotIn(self.key,row['recovery']);self.assertNotIn('eight quiet bowls',row['answer'])
        self.assertNotEqual(self.store.hash_secret(PASSWORD),self.store.hash_secret(PASSWORD))
        self.assertNotIn(PASSWORD.encode(),self.path.read_bytes())
        shop=Ledger(Path(self.tmp.name)/'shop.sqlite3')
        self.assertFalse(shop.db.execute("SELECT 1 FROM sqlite_master WHERE name='attempts'").fetchone());shop.db.close()
    def test_backup_recovery_changes_password_and_invalidates_previous_key(self):
        new_key=self.store.recover('Osmando','Backup key',self.key,NEW)
        self.assertNotEqual(new_key,self.key)
        with self.assertRaises(ValueError):self.store.login('Osmando',PASSWORD)
        self.assertTrue(self.store.login('Osmando',NEW).valid())
        with self.assertRaises(ValueError):self.store.recover('Osmando','Backup key',self.key,PASSWORD)
        self.store.recover('Osmando','Backup key',new_key,PASSWORD)
    def test_question_recovery_is_normalized_and_weak_answers_rejected(self):
        self.store.recover('Osmando','Security question',' EIGHT   QUIET BOWLS ',NEW)
        self.assertTrue(self.store.login('Osmando',NEW).valid())
        with self.assertRaises(ValueError):self.store.set_question(self.store.login('Osmando',NEW),NEW,'Q','short')
    def test_failed_recovery_is_rate_limited_without_changing_password(self):
        for _ in range(3):
            with self.assertRaises(ValueError):self.store.recover('Osmando','Backup key','invalid',NEW)
        with self.assertRaisesRegex(ValueError,'Temporarily locked'):self.store.recover('Osmando','Backup key',self.key,NEW)
        self.assertTrue(self.store.matches(PASSWORD,self.store.owner()['password']))
    def test_admin_changes_require_session_and_current_password(self):
        session=self.store.login('Osmando',PASSWORD)
        with self.assertRaises(PermissionError):self.store.rotate_key(AuthSession(self.store,'fake','Osmando'),PASSWORD)
        with self.assertRaises(ValueError):self.store.change_password(session,'wrong',NEW)
        self.store.change_password(session,PASSWORD,NEW)
        self.assertTrue(self.store.matches(NEW,self.store.owner()['password']))
    def test_email_recovery_requires_bound_identity_and_single_use_proof(self):
        session=self.store.login('Osmando',PASSWORD)
        self.store.bind_email(session,PASSWORD,'https://example.supabase.co','sb_publishable_test','owner@example.com','uid-1')
        with self.assertRaises(ValueError):self.store.email_proof('uid-2','owner@example.com')
        proof=self.store.email_proof('uid-1','owner@example.com')
        self.store.recover('Osmando','Email code',proof,NEW)
        with self.assertRaises(ValueError):self.store.recover('Osmando','Email code',proof,PASSWORD)
    def test_email_client_requests_existing_user_code_and_validates_email(self):
        client=EmailRecovery('https://example.supabase.co','sb_publishable_test','OWNER@example.com');calls=[]
        def request(path,data):
            calls.append((path,data));return {'user':{'id':'uid-1','email':'owner@example.com'}}
        client.client.request=request;client.send();self.assertEqual(client.verify('123456'),'uid-1')
        self.assertEqual(calls[0][1],{'email':'owner@example.com','create_user':False})
        self.assertEqual(calls[1][1]['type'],'email')
        client.client.request=lambda path,data:{'user':{'id':'uid-1','email':'other@example.com'}}
        with self.assertRaises(ValueError):client.verify('123456')

    def test_existing_owner_cannot_be_replaced_by_setup(self):
        with self.assertRaises(ValueError):self.store.setup('Other','Another strong passphrase')
        self.assertEqual(self.store.owner()['name'],'Osmando')
    def test_email_recovery_proof_expires(self):
        session=self.store.login('Osmando',PASSWORD)
        self.store.bind_email(session,PASSWORD,'https://example.supabase.co','sb_publishable_test','owner@example.com','uid-1')
        with patch('time.time',return_value=1000):proof=self.store.email_proof('uid-1','owner@example.com')
        with patch('time.time',return_value=1121):
            with self.assertRaises(ValueError):self.store.recover('Osmando','Email code',proof,NEW)
        self.assertTrue(self.store.matches(PASSWORD,self.store.owner()['password']))

if __name__=='__main__':unittest.main()
