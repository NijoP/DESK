"""Tests for DESK Authentication and Security Infrastructure."""

import os
import sys
import unittest
import tempfile
import shutil
from desk.auth.storage import (
    InMemoryCredentialStore,
    ProtectedFileCredentialStore,
    WindowsCredentialStore,
)
from desk.auth.broker import CredentialBroker, ProviderStatus


class TestCredentialStorage(unittest.TestCase):
    def test_in_memory_store(self):
        store = InMemoryCredentialStore()
        self.assertIsNone(store.get("lcsc", "default"))
        
        ok = store.set("lcsc", "default", "secret_token_123")
        self.assertTrue(ok)
        self.assertEqual(store.get("lcsc", "default"), "secret_token_123")
        
        creds = store.list()
        self.assertEqual(len(creds), 1)
        self.assertEqual(creds[0]["service"], "lcsc")
        self.assertEqual(creds[0]["account"], "default")
        
        deleted = store.delete("lcsc", "default")
        self.assertTrue(deleted)
        self.assertIsNone(store.get("lcsc", "default"))
        self.assertEqual(len(store.list()), 0)

    def test_protected_file_store(self):
        tmp_dir = tempfile.mkdtemp()
        vault_path = os.path.join(tmp_dir, "test_vault.json")
        try:
            store = ProtectedFileCredentialStore(vault_path)
            self.assertTrue(os.path.exists(vault_path))

            ok = store.set("jlcpcb", "team", "apiKey_998877")
            self.assertTrue(ok)
            
            # File should not contain raw secret in plaintext
            with open(vault_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertNotIn("apiKey_998877", content)

            read_secret = store.get("jlcpcb", "team")
            self.assertEqual(read_secret, "apiKey_998877")

            # Test list
            lst = store.list()
            self.assertEqual(len(lst), 1)
            self.assertEqual(lst[0]["service"], "jlcpcb")

            # Test delete
            del_ok = store.delete("jlcpcb", "team")
            self.assertTrue(del_ok)
            self.assertIsNone(store.get("jlcpcb", "team"))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @unittest.skipUnless(sys.platform == "win32", "Windows Credential Manager is Windows-only")
    def test_windows_credential_store(self):
        try:
            store = WindowsCredentialStore()
        except Exception as e:
            self.skipTest(f"Windows Credential Manager unavailable: {e}")

        test_svc = "desk_test_suite_svc"
        test_acc = "test_agent"
        test_val = "super_secure_win32_token_xyz"

        # Cleanup if previously left over
        store.delete(test_svc, test_acc)

        try:
            ok = store.set(test_svc, test_acc, test_val)
            self.assertTrue(ok)
            retrieved = store.get(test_svc, test_acc)
            self.assertEqual(retrieved, test_val)
        finally:
            del_ok = store.delete(test_svc, test_acc)
            self.assertTrue(del_ok)
            self.assertIsNone(store.get(test_svc, test_acc))


class TestCredentialBroker(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryCredentialStore()
        self.broker = CredentialBroker(store=self.store)

    def test_missing_credentials_fails_closed(self):
        with self.assertRaises(PermissionError) as ctx:
            self.broker.get_auth_headers("lcsc")
        self.assertIn("Missing credentials for 'lcsc'", str(ctx.exception))
        self.assertIn("auth configure lcsc", str(ctx.exception))

    def test_minting_headers_and_status(self):
        status = self.broker.get_provider_status("lcsc")
        self.assertEqual(status["status"], ProviderStatus.NOT_CONFIGURED)
        self.assertFalse(status["authenticated"])

        # Configure
        self.broker.store_credentials("lcsc", "default", "lcsc_secret_token_abc")
        
        status_after = self.broker.get_provider_status("lcsc")
        self.assertEqual(status_after["status"], ProviderStatus.AVAILABLE)
        self.assertTrue(status_after["authenticated"])

        headers = self.broker.get_auth_headers("lcsc")
        self.assertEqual(headers["Authorization"], "Bearer lcsc_secret_token_abc")
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_secret_scrubbing(self):
        secret = "secret_jlcpcb_token_49102"
        self.broker.store_credentials("jlcpcb", "default", secret)
        
        # Verify secret is tracked and redacted
        log_msg = f"Request failed with token {secret} to https://api.jlcpcb.com"
        scrubbed = self.broker.scrub(log_msg)
        self.assertNotIn(secret, scrubbed)
        self.assertIn("[REDACTED_SECRET]", scrubbed)

        # Generic bearer token redaction
        generic_msg = "Authorization: Bearer 98a7sdf89a7sdf89asd7f in header"
        scrubbed_generic = self.broker.scrub(generic_msg)
        self.assertNotIn("98a7sdf89a7sdf89asd7f", scrubbed_generic)
        self.assertIn("[REDACTED_TOKEN]", scrubbed_generic)

    def test_provider_headers(self):
        self.broker.store_credentials("mouser", "default", "mouser_key_111")
        mouser_headers = self.broker.get_auth_headers("mouser")
        self.assertEqual(mouser_headers["apiKey"], "mouser_key_111")

        self.broker.store_credentials("digikey", "default", "digikey_client_222")
        digikey_headers = self.broker.get_auth_headers("digikey")
        self.assertEqual(digikey_headers["X-DIGIKEY-Client-Id"], "digikey_client_222")


if __name__ == "__main__":
    unittest.main()
