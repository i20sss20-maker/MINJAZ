"""Sandbox demo catalog seeding must preserve every administrator's choices."""
import unittest
from scripts.seed_digital_services_preview import SAMPLES, seed_packages

class FakeSeedCursor:
    def __init__(self, packages=None):
        # Simulate PostgreSQL INSERT ... ON CONFLICT DO NOTHING.
        self.packages=dict(packages or {})
        self.reads=0
        self.inserts=0
    def execute(self, sql, params):
        if "INSERT INTO digital_service_packages" in sql:
            slug = params[0]
            if slug not in self.packages:
                self.packages[slug] = True
                self.inserts += 1
        elif "SELECT slug, active FROM digital_service_packages" in sql:
            self.reads += 1
            self._rows = [(slug, self.packages[slug]) for slug in params[0] if slug in self.packages]
        else:
            raise AssertionError("Unexpected query in preview seed: " + sql)
    def fetchall(self):
        return self._rows

class DigitalSeedTests(unittest.TestCase):
    def test_empty_catalog_gets_three_active_samples(self):
        cursor = FakeSeedCursor()
        result = seed_packages(cursor)
        self.assertEqual(result, {"present":3,"active":3,"hidden":0})
        self.assertEqual(cursor.inserts,3)
    def test_second_seed_does_not_duplicate(self):
        cursor = FakeSeedCursor()
        seed_packages(cursor)
        self.assertEqual(seed_packages(cursor), {"present":3,"active":3,"hidden":0})
        self.assertEqual(cursor.inserts,3)
    def test_admin_hidden_demo_remains_hidden_and_does_not_fail_deployment(self):
        slug = SAMPLES[0][0]
        cursor = FakeSeedCursor({slug:False})
        result = seed_packages(cursor)
        self.assertEqual(result, {"present":3,"active":2,"hidden":1})
        self.assertIs(cursor.packages[slug],False)
        self.assertEqual(cursor.inserts,2)
    def test_all_demo_packages_may_be_hidden_without_failure(self):
        cursor = FakeSeedCursor({sample[0]:False for sample in SAMPLES})
        self.assertEqual(seed_packages(cursor), {"present":3,"active":0,"hidden":3})
        self.assertEqual(cursor.inserts,0)
    def test_custom_non_demo_package_is_preserved(self):
        cursor = FakeSeedCursor({"custom-client-package":False})
        seed_packages(cursor)
        self.assertIs(cursor.packages["custom-client-package"],False)
        self.assertEqual(len(cursor.packages),4)

if __name__ == "__main__":
    unittest.main()
