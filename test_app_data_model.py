import tempfile
import unittest
from pathlib import Path

from main import DataStore


class DataStoreTests(unittest.TestCase):
    def setUp(self):
        temp_dir = Path(tempfile.mkdtemp())
        self.data_path = temp_dir / "dam_data.json"
        self.store = DataStore(self.data_path)

    def test_seed_admin_user_created(self):
        users = self.store.list_users()
        admin_users = [user for user in users if user["role"] == "admin"]
        self.assertTrue(admin_users)

    def test_register_and_authenticate_user(self):
        user = self.store.register_user("Jane Smith", "jane@example.com", "secret123", "user")
        self.assertEqual(user["email"], "jane@example.com")
        self.assertIsNotNone(self.store.authenticate("jane@example.com", "secret123"))
        self.assertIsNone(self.store.authenticate("jane@example.com", "incorrect"))

    def test_register_admin_role(self):
        admin = self.store.register_user("Morgan Admin", "morgan@example.com", "secret123", "admin")
        self.assertEqual(admin["role"], "admin")

    def test_password_reset(self):
        user = self.store.register_user("Jane Smith", "jane@example.com", "secret123", "user")
        self.assertNotIn("password_hash", user)
        self.assertNotIn("password_hint", user)
        self.assertTrue(self.store.reset_password("jane@example.com", "newsecret"))
        self.assertIsNone(self.store.authenticate("jane@example.com", "secret123"))
        self.assertIsNotNone(self.store.authenticate("jane@example.com", "newsecret"))

    def test_asset_review_and_usage_right_records(self):
        user = self.store.register_user("Alice User", "alice@example.com", "password", "user")
        asset = self.store.add_asset(
            asset_name="Brochure Banner",
            description="Fall campaign banner",
            category="Marketing",
            file_path="/tmp/banner.png",
            uploaded_by=user["user_id"],
        )
        review = self.store.add_review(asset["asset_id"], user["user_id"], "Approved", "Looks good")
        usage = self.store.add_usage_right(asset["asset_id"], "internal", "2027-12-31", "Do not resell")

        self.assertEqual(asset["status"], "Pending Review")
        self.assertEqual(asset["description"], "Fall campaign banner")
        self.assertEqual(asset["uploaded_by"], user["user_id"])
        self.assertTrue(asset["upload_date"])
        self.assertEqual(len(self.store.list_assets(user["user_id"], "user")), 1)
        self.assertEqual(len(self.store.list_assets("another-user", "user")), 0)
        self.assertEqual(review["decision"], "Approved")
        self.assertEqual(len(self.store.list_reviews(asset["asset_id"])), 1)
        self.assertEqual(usage["asset_id"], asset["asset_id"])
        self.assertEqual(usage["approved_for"], "internal")


if __name__ == "__main__":
    unittest.main()
