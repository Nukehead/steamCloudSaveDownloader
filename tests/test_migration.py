import pytest
import datetime
import sqlite3
import os
from steamCloudSaveDownloader.db import db
from steamCloudSaveDownloader.migration import DatabaseMigrator

class DummyStorage:
    def rename_legacy_backups(self, app_id):
        pass

def test_v0_to_v1_migration_strips_timezone(tmp_path):
    # Initialize a raw db
    db_loc = str(tmp_path)
    db_ = db(db_loc)

    # Force DB back to version 0 and clear everything
    db_.set_db_version(0)
    cur = db_.con.cursor()
    cur.execute("DELETE FROM VERSION")
    cur.execute("DELETE FROM FILES")
    cur.execute("DELETE FROM GAMES")

    # Insert a dummy game and file
    cur.execute("INSERT INTO GAMES VALUES (1, 'Test Game', 'Test Dir');")
    cur.execute("INSERT INTO FILES VALUES (1, 'test.sav', 'test/path', 1);")

    # Insert a raw V0 timestamp string exactly as old scsd would have stored it
    # E.g. "2026-08-25 13:41:00" (PST time, no timezone info)
    cur.execute("INSERT INTO VERSION (version_id, file_id, time, version_num) VALUES (1, 1, '2026-08-25 13:41:00', 1);")
    db_.con.commit()

    # Run the migrator
    migrator = DatabaseMigrator(db_, DummyStorage())
    migrator.run(manual=False)

    # Assert version bumped to 1
    assert db_.get_db_version() >= 1

    # Assert the raw text stored in the database does NOT contain "+00:00"
    # and properly converted to 20:41 (UTC)
    res = cur.execute("SELECT CAST(time AS TEXT) FROM VERSION WHERE version_id = 1;")
    raw_time_str = res.fetchone()[0]

    assert "+00:00" not in raw_time_str, f"Migrated timestamp contains timezone suffix: {raw_time_str}"
    assert raw_time_str.startswith("2026-08-25T20:41:00"), f"Timestamp was not correctly converted to UTC: {raw_time_str}"
