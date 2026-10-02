import pytest
import datetime
from unittest.mock import patch, MagicMock
from steamCloudSaveDownloader.stored import stored
from steamCloudSaveDownloader.db import db

def test_stored_handles_none_dates_without_crashing(capsys, tmp_path):
    # Prepare dummy DB with None dates
    db_loc = str(tmp_path)
    db_ = db(db_loc)
    cur = db_.con.cursor()
    cur.execute("INSERT INTO GAMES VALUES (1, 'Test Game', 'testdir');")
    cur.execute("INSERT INTO FILES VALUES (1, 'test.sav', '', 1);")
    # Insert None for time
    cur.execute("INSERT INTO VERSION (version_id, file_id, time, version_num) VALUES (1, 1, NULL, 1);")
    db_.con.commit()

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
    cur = db_.con.cursor()
    cur.execute("INSERT INTO GAMES VALUES (1, 'Test Game', 'testdir');")
    cur.execute("INSERT INTO FILES VALUES (1, 'test.sav', '', 1);")

    t1 = datetime.datetime(2026, 10, 2, 10, 0, 0)
    t2 = datetime.datetime(2026, 10, 1, 10, 0, 0)

    # In V2, all version_num are 0
    cur.execute("INSERT INTO VERSION (version_id, file_id, time, version_num) VALUES (1, 1, ?, 0);", (t1,))
    cur.execute("INSERT INTO VERSION (version_id, file_id, time, version_num) VALUES (2, 1, ?, 0);", (t2,))
    db_.con.commit()

    s = stored(staged_args=[], save_dir=db_loc)
    s.db = db_
    s.get_result()

    captured = capsys.readouterr()
    lines = captured.out.split('\n')
    active_lines = [l for l in lines if "(active)" in l]
    backup_lines = [l for l in lines if "backup:" in l]

    assert len(active_lines) == 1
    assert len(backup_lines) == 1
