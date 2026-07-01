import unittest

from chatview.index import _post_process_db_refresh


class TestFtsPostProcess(unittest.TestCase):
    def _db(self, integrity=True):
        class FakeDb:
            rebuild_count = 0
            aggregate_count = 0

            def verify_fts_integrity(self):
                return integrity

            def rebuild_fts(self):
                self.rebuild_count += 1

            def refresh_aggregates(self):
                self.aggregate_count += 1

        return FakeDb()

    def test_normal_changed_refresh_skips_full_rebuild_when_fts_is_valid(self):
        db = self._db(integrity=True)

        _post_process_db_refresh(db, force=False, changed=True)

        self.assertEqual(db.rebuild_count, 0)
        self.assertEqual(db.aggregate_count, 1)

    def test_force_refresh_rebuilds_fts(self):
        db = self._db(integrity=True)

        _post_process_db_refresh(db, force=True, changed=True)

        self.assertEqual(db.rebuild_count, 1)
        self.assertEqual(db.aggregate_count, 1)

    def test_integrity_failure_rebuilds_fts(self):
        db = self._db(integrity=False)

        _post_process_db_refresh(db, force=False, changed=True)

        self.assertEqual(db.rebuild_count, 1)
        self.assertEqual(db.aggregate_count, 1)

    def test_unchanged_refresh_does_nothing(self):
        db = self._db(integrity=False)

        _post_process_db_refresh(db, force=False, changed=False)

        self.assertEqual(db.rebuild_count, 0)
        self.assertEqual(db.aggregate_count, 0)


if __name__ == "__main__":
    unittest.main()
