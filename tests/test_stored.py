import pytest
import datetime
from unittest.mock import patch, MagicMock
from steamCloudSaveDownloader.stored import stored
from steamCloudSaveDownloader.db import db

def test_stored_handles_none_dates_without_crashing(capsys, tmp_path):
    # Prepare dummy DB with None dates
    db_loc = str(tmp_path)
    db_ = db(db_loc)
    from .helpers import seed_game, seed_file, seed_version
    seed_game(db_, 1, 'Test Game', 'testdir')
    file_id = seed_file(db_, 'test.sav', '', 1)
    # Insert None for time
    seed_version(db_, file_id, None, 1)

    s = stored(staged_args=[], save_dir=db_loc)
    s.db = db_

    # Run get_result which caused the crash previously
    s.get_result()

    captured = capsys.readouterr()
    assert "None" in captured.out
    assert "(active)" in captured.out


def test_stored_handles_multiple_versions(capsys, tmp_path):
    db_loc = str(tmp_path)
    db_ = db(db_loc)
    from .helpers import seed_game, seed_file, seed_version
    seed_game(db_, 1, 'Test Game', 'testdir')
    file_id = seed_file(db_, 'test.sav', '', 1)

    t1 = datetime.datetime(2026, 10, 2, 10, 0, 0)
    t2 = datetime.datetime(2026, 10, 1, 10, 0, 0)

    # In V2, all version_num are 0
    seed_version(db_, file_id, t1, 0)
    seed_version(db_, file_id, t2, 0)

    s = stored(staged_args=[], save_dir=db_loc)
    s.db = db_
    s.get_result()

    captured = capsys.readouterr()
    lines = captured.out.split('\n')
    active_lines = [l for l in lines if "(active)" in l]
    backup_lines = [l for l in lines if "backup:" in l]

    assert len(active_lines) == 1
    assert len(backup_lines) == 1

def test_stored_handles_v1_legacy_versions(capsys, tmp_path):
    db_loc = str(tmp_path)
    db_ = db(db_loc)
    db_.set_db_version(1)
    from .helpers import seed_game, seed_file, seed_version
    seed_game(db_, 1, 'Legacy Game', 'legacydir')
    file_id = seed_file(db_, 'legacy.sav', '', 1)

    t1 = datetime.datetime(2026, 10, 2, 10, 0, 0)
    t2 = datetime.datetime(2026, 10, 1, 10, 0, 0)

    # In V1, active is version 0, backup is version 1
    seed_version(db_, file_id, t1, 0)
    seed_version(db_, file_id, t2, 1)

    s = stored(staged_args=[], save_dir=db_loc)
    s.db = db_
    s.get_result()

    captured = capsys.readouterr()
    lines = captured.out.split('\n')
    active_lines = [l for l in lines if "(active)" in l]
    backup_lines = [l for l in lines if "backup: .scsd_1" in l]

    assert len(active_lines) == 1, "Should have one active line"
    assert len(backup_lines) == 1, "Should have one .scsd_1 backup line"
