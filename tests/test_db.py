import steamCloudSaveDownloader.db as db
from .helpers import seed_game, seed_file, seed_version

import datetime
import os
import pytest

def test_db_creation_and_schema(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=5)
    assert os.path.isfile(os.path.join(db_loc, db.DB_FILENAME))
    assert db_.schema_ok()

def test_request_count(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=5)
    db_.add_requests_count(0xfffffff)
    del db_
    db_ = db.db(db_location=db_loc, rotation=5)
    assert db_.is_requests_limit_exceed()

def test_add_game(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=5)
    db_.add_new_game(3939, "test_game")
    assert db_.is_game_exist(3939)
    assert db_.get_stored_game_names([]) == {(3939, "test_game")}

def test_set_game_dir(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=5)
    db_.add_new_game(3939, "test_game")
    db_.set_game_dir(3939, "./achaka")
    assert db_.get_game_dir(3939) == "./achaka"

def test_add_files(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=5)
    db_.add_new_game(3939, "test_game")
    # Expect [(filename, path, app_id, last_update_time), ...]
    payload = [
        ("fileA", "./", 3939, datetime.datetime(2009, 8, 31)),
        ("fileB", "./test", 3939, datetime.datetime(2019, 1, 2)),
        ("C", "./dir", 3939, datetime.datetime(2019, 3, 9, 3, 9, 3))
    ]
    db_.add_new_files(payload)
    assert db_.get_file_id(3939, "./", "fileA") is not None
    assert db_.get_file_id(3939, "./test", "fileB") is not None
    assert db_.get_file_id(3939, "./dir", "C") is not None

def test_outdated(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=5)
    db_.add_new_game(3939, "test_game")
    file_id = seed_file(db_, "fileA", "./", 3939)
    seed_version(db_, file_id, datetime.datetime(2009, 8, 31), 0)

    outdated_1, db_time_1 = db_.is_file_outdated(file_id, datetime.datetime(2009, 8, 31, tzinfo=datetime.timezone.utc))
    assert outdated_1 == False
    assert db_time_1 == datetime.datetime(2009, 8, 31, tzinfo=datetime.timezone.utc)

    outdated_2, db_time_2 = db_.is_file_outdated(file_id, datetime.datetime(2012, 12, 12, tzinfo=datetime.timezone.utc))
    assert outdated_2 == True
    assert db_time_2 == datetime.datetime(2009, 8, 31, tzinfo=datetime.timezone.utc)

def test_update_version_time(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=5)
    db_.add_new_game(3939, "test_game")
    file_id = seed_file(db_, "fileA", "./", 3939)

    datetime_ = datetime.datetime(2009, 8, 31)
    for i in range(7):
        db_.update_file_update_time_to_now(file_id, datetime_)
        datetime_ = datetime_ + datetime.timedelta(1)

    cur = db_.con.cursor()
    res = cur.execute("SELECT time FROM VERSION WHERE file_id = ? ORDER BY time DESC;", (file_id,))
    result = res.fetchall()
    assert len(result) == 7
    assert result[0][0] == datetime.datetime(2009, 9, 6)
    assert result[-1][0] == datetime.datetime(2009, 8, 31)

def test_remove_outdated(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=2)
    db_.add_new_game(3939, "test_game")
    file_id = seed_file(db_, "fileA", "./", 3939)

    # Insert 7 versions
    datetime_ = datetime.datetime(2009, 8, 31)
    for i in range(7):
        db_.update_file_update_time_to_now(file_id, datetime_)
        datetime_ = datetime_ + datetime.timedelta(1)

    outdated = db_.remove_outdated_file(file_id)
    assert len(outdated) == 5

    cur = db_.con.cursor()
    res = cur.execute("SELECT time FROM VERSION WHERE file_id = ? ORDER BY time DESC;", (file_id,))
    result = res.fetchall()
    assert len(result) == 2
    assert result[0][0] == datetime.datetime(2009, 9, 6)
    assert result[1][0] == datetime.datetime(2009, 9, 5)

def test_get_file_version_by_file_id(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=2)
    db_.add_new_game(3939, "test_game")
    file_id = seed_file(db_, "fileA", "./", 3939)

    db_.update_file_update_time_to_now(file_id, datetime.datetime(2009, 9, 5))
    db_.update_file_update_time_to_now(file_id, datetime.datetime(2009, 9, 6))

    versions = db_.get_file_version_by_file_id(file_id)
    assert len(versions) == 2
    # Check that ordinal is not derived dynamically anymore: both active and backup get 0 in DB v2
    assert versions[0][0] == datetime.datetime(2009, 9, 6)
    assert versions[0][1] == 0
    assert versions[1][0] == datetime.datetime(2009, 9, 5)
    assert versions[1][1] == 0

def test_get_latest_file_version_time(tmp_path):
    db_loc = str(tmp_path)
    db_ = db.db(db_location=db_loc, rotation=2)
    db_.add_new_game(3939, "test_game")
    file_id = seed_file(db_, "fileA", "./", 3939)

    db_.update_file_update_time_to_now(file_id, datetime.datetime(2009, 9, 5))
    db_.update_file_update_time_to_now(file_id, datetime.datetime(2009, 9, 6))

    latest_time = db_.get_latest_file_version_time(file_id)
    assert latest_time == datetime.datetime(2009, 9, 6, tzinfo=datetime.timezone.utc)
