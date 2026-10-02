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
    assert "(backup: .scsd_1)" in captured.out
