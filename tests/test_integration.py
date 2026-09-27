import os
import datetime
import pytest
from unittest.mock import MagicMock
from steamCloudSaveDownloader import db, storage, summary
from steamCloudSaveDownloader.__main__ import update_game

@pytest.fixture
def integration_env(tmp_path):
    save_dir = str(tmp_path / "data")
    os.makedirs(save_dir, exist_ok=True)
    db_ = db.db(db_location=save_dir, rotation=2)
    storage_ = storage.storage(location=save_dir, db_=db_)
    summary_ = summary.summary(summary.level_e.TIME)
    return save_dir, db_, storage_, summary_

def create_mock_web(cloud_files):
    mock_web = MagicMock()
    mock_web.get_game_save.return_value = cloud_files

    def mock_download(link, target, mtime):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        content = f"content_of_{link}"
        with open(target, "w") as f:
            f.write(content)
        ts = mtime.timestamp()
        os.utime(target, (ts, ts))

    mock_web.download_game_save.side_effect = mock_download
    return mock_web

def test_fresh_game_download_flow(integration_env):
    save_dir, db_, storage_, summary_ = integration_env
    app_id = 1010
    game = {'name': 'FreshGame', 'app_id': app_id, 'link': 'https://mock/game/1010'}

    t1 = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    t2 = datetime.datetime(2026, 1, 2, 14, 30, 0, tzinfo=datetime.timezone.utc)

    cloud_files = [
        {'filename': 'save1.dat', 'link': 'dl_save1', 'time': t1, 'path': './'},
        {'filename': 'sub_save.dat', 'link': 'dl_sub_save', 'time': t2, 'path': 'subfolder'}
    ]
    mock_web = create_mock_web(cloud_files)

    # Run update_game on a fresh DB
    update_game(db_, storage_, mock_web, game, summary_)

    # 1. DB checks
    assert db_.is_game_exist(app_id)
    assert db_.get_game_dir(app_id) == str(app_id)
    file1_id = db_.get_file_id(app_id, './', 'save1.dat')
    file2_id = db_.get_file_id(app_id, 'subfolder', 'sub_save.dat')
    assert file1_id is not None
    assert file2_id is not None

    # Check version rows
    assert len(db_.get_file_version_by_file_id(file1_id)) == 1
    assert len(db_.get_file_version_by_file_id(file2_id)) == 1

    # 2. Filesystem checks
    file1_path = os.path.join(save_dir, str(app_id), 'save1.dat')
    file2_path = os.path.join(save_dir, str(app_id), 'subfolder', 'sub_save.dat')
    assert os.path.isfile(file1_path)
    assert os.path.isfile(file2_path)
    with open(file1_path, 'r') as f:
        assert f.read() == 'content_of_dl_save1'
    with open(file2_path, 'r') as f:
        assert f.read() == 'content_of_dl_sub_save'

    # 3. Summary check
    assert len(summary_.data) == 1
    assert summary_.data[0]['name'] == 'FreshGame'
    assert len(summary_.data[0]['files']) == 2

def test_v0_migration_update_and_rotation_flow(integration_env):
    """
    End-to-end integration test with:
    - Pre-populated DB and v0 files (.scsd_1) on disk.
    - Mocked Steam Cloud providing a newer save file version.
    - Verifying:
        1. V0 numbered backup is migrated to timestamp format.
        2. Previous active file is rotated to timestamp format.
        3. New version is downloaded as the active file.
        4. Outdated backup beyond rotation limit (2) is pruned.
    """
    save_dir, db_, storage_, summary_ = integration_env
    app_id = 2020
    game = {'name': 'V0RPG', 'app_id': app_id, 'link': 'https://mock/game/2020'}

    t1 = datetime.datetime(2025, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    t2 = datetime.datetime(2025, 6, 2, 10, 0, 0, tzinfo=datetime.timezone.utc)
    t3 = datetime.datetime(2025, 6, 3, 10, 0, 0, tzinfo=datetime.timezone.utc)

    # 1. Prep DB with an existing game and 2 versions
    db_.add_new_game(app_id, 'V0RPG')
    db_.set_game_dir(app_id, str(app_id))
    cur = db_.con.cursor()
    cur.execute("INSERT INTO FILES VALUES (NULL, ?, ?, ?);", ('save.sav', './', app_id))
    file_id = cur.lastrowid
    # v2 is active (0), v1 is older (1) in v0 scheme
    cur.execute("INSERT INTO VERSION VALUES (NULL, ?, ?, ?);", (file_id, t2.replace(tzinfo=None), 0))
    cur.execute("INSERT INTO VERSION VALUES (NULL, ?, ?, ?);", (file_id, t1.replace(tzinfo=None), 1))
    db_.con.commit()

    # 2. Prep disk state: active save.sav and v0 backup save.sav.scsd_1
    game_dir = os.path.join(save_dir, str(app_id))
    os.makedirs(game_dir, exist_ok=True)
    active_path = os.path.join(game_dir, 'save.sav')
    v0_backup_path = os.path.join(game_dir, 'save.sav.scsd_1')
    with open(active_path, 'w') as f:
        f.write('v2_active_content')
    with open(v0_backup_path, 'w') as f:
        f.write('v1_v0_backup_content')

    # 3. Setup mock web returning v3 from Steam Cloud
    cloud_files = [
        {'filename': 'save.sav', 'link': 'dl_v3_content', 'time': t3, 'path': './'}
    ]
    mock_web = create_mock_web(cloud_files)

    # 4. Execute update_game
    update_game(db_, storage_, mock_web, game, summary_)

    # 5. Assertions:
    # A) V0 .scsd_1 should have been migrated to .scsd_20250601_100000,
    #    BUT because rotation is 2 (keeping v3 and v2), v1 should have been pruned afterwards!
    migrated_v1_path = os.path.join(game_dir, 'save.sav.scsd_20250601_100000')
    assert not os.path.exists(v0_backup_path), "V0 .scsd_1 file was not cleaned up"
    assert not os.path.exists(migrated_v1_path), "v1 should have been pruned under rotation=2"

    # B) v2 should be rotated to timestamped backup: .scsd_20250602_100000
    rotated_v2_path = os.path.join(game_dir, 'save.sav.scsd_20250602_100000')
    assert os.path.isfile(rotated_v2_path), "v2 was not rotated to timestamp format"
    with open(rotated_v2_path, 'r') as f:
        assert f.read() == 'v2_active_content'

    # C) New active file save.sav should contain v3 content
    assert os.path.isfile(active_path)
    with open(active_path, 'r') as f:
        assert f.read() == 'content_of_dl_v3_content'

    # D) Database should now have exactly 2 versions (v3 and v2)
    versions = db_.get_file_version_by_file_id(file_id)
    assert len(versions) == 2
    assert versions[0][0] == t3.replace(tzinfo=None)
    assert versions[0][1] == 0
    assert versions[1][0] == t2.replace(tzinfo=None)
    assert versions[1][1] == 1

def test_no_op_when_file_unchanged(integration_env):
    save_dir, db_, storage_, summary_ = integration_env
    app_id = 3030
    game = {'name': 'StableGame', 'app_id': app_id, 'link': 'https://mock/game/3030'}
    t1 = datetime.datetime(2026, 3, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)

    cloud_files = [
        {'filename': 'save.sav', 'link': 'dl_link', 'time': t1, 'path': './'}
    ]
    mock_web = create_mock_web(cloud_files)

    # Initial download
    update_game(db_, storage_, mock_web, game, summary_)
    assert len(summary_.data[0]['files']) == 1

    # Second run with identical time
    mock_web.download_game_save.reset_mock()
    summary2 = summary.summary(summary.level_e.TIME)
    update_game(db_, storage_, mock_web, game, summary2)

    # download_game_save must not be called again
    mock_web.download_game_save.assert_not_called()
    assert len(summary2.data) == 0
