import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend import main


class AuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "campus_customs.db"
        shutil.copyfile(main.DB_PATH, self.database_path)
        self.original_database_path = main.DB_PATH
        main.DB_PATH = self.database_path
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.DB_PATH = self.original_database_path
        self.temp_dir.cleanup()

    def test_seed_user_can_log_in_and_legacy_hash_is_upgraded(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"email": "test@campuscustoms.yale.edu", "password": "password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "test@campuscustoms.yale.edu")
        self.assertNotIn("password_hash", response.json())
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        with sqlite3.connect(self.database_path) as connection:
            password_hash = connection.execute(
                "SELECT password_hash FROM users WHERE email = ?",
                ("test@campuscustoms.yale.edu",),
            ).fetchone()[0]
        self.assertEqual(len(password_hash.split("$")), 4)
        self.assertEqual(password_hash.split("$")[1], "600000")

        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_registration_login_and_duplicate_email(self) -> None:
        account = {
            "first_name": "New",
            "last_name": "Shopper",
            "email": "New.Shopper@example.com",
            "password": "a-long-and-unique-passphrase",
        }
        response = self.client.post("/api/auth/register", json=account)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["first_name"], "New")
        self.assertEqual(response.json()["last_name"], "Shopper")
        self.assertNotIn("password_hash", response.json())
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        with sqlite3.connect(self.database_path) as connection:
            stored_hash = connection.execute(
                "SELECT password_hash FROM users WHERE email = ?",
                ("new.shopper@example.com",),
            ).fetchone()[0]
        self.assertNotEqual(stored_hash, account["password"])
        self.assertEqual(stored_hash.split("$")[1], "600000")

        self.client.post("/api/auth/logout")
        login_response = self.client.post(
            "/api/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()["email"], "new.shopper@example.com")

        duplicate = self.client.post("/api/auth/register", json=account)
        self.assertEqual(duplicate.status_code, 409)

    def test_bad_credentials_are_rejected(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"email": "test@campuscustoms.yale.edu", "password": "not-the-password"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)


if __name__ == "__main__":
    unittest.main()