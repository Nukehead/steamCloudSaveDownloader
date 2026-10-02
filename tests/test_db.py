import steamCloudSaveDownloader.db as db

import datetime
import os
import pytest

@pytest.fixture(scope='session')
def tmp_location(tmp_path_factory):
    return tmp_path_factory.getbasetemp()

class TestDB:
    def test_db_creation_and_schema(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=5)
        assert os.path.isfile(os.path.join(tmp_location, db.DB_FILENAME))

    def test_request_count(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=5)
        db_.add_requests_count(0xfffffff)
        del db_
        db_ = db.db(db_location=tmp_location, rotation=5)
        assert db_.is_requests_limit_exceed()

    def test_add_game(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=5)
        db_.add_new_game(3939, "test_game")
        assert db_.is_game_exist(3939)
        assert db_.get_stored_game_names([]) == {(3939, "test_game")}

    def test_set_game_dir(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=5)
        db_.set_game_dir(3939, "./achaka")
        assert db_.get_game_dir(3939) == "./achaka"

    def test_add_files(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=5)
        # Expect [(filename, path, app_id, last_update_time), ...]
        payload = [
            ("fileA", "./", 3939, datetime.datetime(2009, 8, 31)),
            ("fileB", "./test", 3939, datetime.datetime(2019, 1, 2)),
            ("C", "./dir", 3939, datetime.datetime(2019, 3, 9, 3, 9, 3))
        ]
        db_.add_new_files(payload)
        assert db_.get_file_id(3939, "./", "fileA") == 1
        assert db_.get_file_id(3939, "./test", "fileB") == 2
        assert db_.get_file_id(3939, "./dir", "C") == 3

    def test_outdated(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=5)
        assert db_.is_file_outdated(1, datetime.datetime(2009, 8, 31, tzinfo=datetime.timezone.utc)) == (False, datetime.datetime(2009, 8, 31, tzinfo=datetime.timezone.utc))
        assert db_.is_file_outdated(1, datetime.datetime(2012, 12, 12, tzinfo=datetime.timezone.utc)) == (True, datetime.datetime(2009, 8, 31, tzinfo=datetime.timezone.utc))

    def test_update_version_time(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=5)
        datetime_ = datetime.datetime(2009, 8, 31)
        for i in range(6):
            datetime_ = datetime_ + datetime.timedelta(1)
            db_.update_file_update_time_to_now(1, datetime_)
        cur = db_.con.cursor()
        res = cur.execute("SELECT time FROM VERSION WHERE file_id = ? ORDER BY time DESC;", (1,))
        result = res.fetchall()
        assert len(result) == 7
        assert result[-1][0] == datetime.datetime(2009, 8, 31)
        assert result[0][0] == datetime.datetime(2009, 9, 6)

    def test_remove_outdated(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=2)
        outdated = db_.remove_outdated_file(1)
        assert len(outdated) == 5
        cur = db_.con.cursor()
        res = cur.execute("SELECT time FROM VERSION WHERE file_id = ? ORDER BY time DESC;", (1,))
        result = res.fetchall()
        assert len(result) == 2
        assert result[0][0] == datetime.datetime(2009, 9, 6)
        assert result[1][0] == datetime.datetime(2009, 9, 5)

    def test_get_file_version_by_file_id(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=2)
        versions = db_.get_file_version_by_file_id(1)
        assert len(versions) == 2
        # Check that ordinal is derived dynamically: newest is 0, next is 1
        assert versions[0][0] == datetime.datetime(2009, 9, 6)
        assert versions[0][1] == 0
        assert versions[1][0] == datetime.datetime(2009, 9, 5)
        assert versions[1][1] == 0

    def test_get_latest_file_version_time(self, tmp_location):
        db_ = db.db(db_location=tmp_location, rotation=2)
        latest_time = db_.get_latest_file_version_time(1)
        assert latest_time == datetime.datetime(2009, 9, 6, tzinfo=datetime.timezone.utc)
