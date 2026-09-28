import os
import datetime
import pytest
from steamCloudSaveDownloader import db, storage

@pytest.fixture
def storage_env(tmp_path):
    save_dir = str(tmp_path / "saves")
    os.makedirs(save_dir, exist_ok=True)
    db_ = db.db(db_location=save_dir, rotation=2)
    storage_ = storage.storage(location=save_dir, db_=db_)
    return save_dir, db_, storage_

def test_version_suffix(storage_env):
    _, _, s = storage_env
    assert s.get_version_suffix(0) == ""
    assert s.get_version_suffix(None) == ""
    dt = datetime.datetime(2026, 9, 25, 19, 30, 0)
    assert s.get_version_suffix(dt) == ".scsd_20260925_193000"
    assert s.get_version_suffix("2026-09-25 19:30:00") == ".scsd_20260925_193000"
    # v0 int support
    assert s.get_version_suffix(1) == ".scsd_1"

def test_get_filename_location(storage_env):
    save_dir, db_, s = storage_env
    app_id = 12345
    db_.add_new_game(app_id, "TestGame")
    s.create_game_folder("TestGame", app_id)

    loc_active = s.get_filename_location(app_id, "save.dat", "./")
    assert os.path.normpath(loc_active) == os.path.normpath(os.path.join(save_dir, str(app_id), "save.dat"))

    dt = datetime.datetime(2026, 9, 25, 19, 30, 0)
    loc_backup = s.get_filename_location(app_id, "save.dat", "./", dt)
    assert os.path.normpath(loc_backup) == os.path.normpath(os.path.join(save_dir, str(app_id), "save.dat.scsd_20260925_193000"))

def test_v0_file_cleanup(storage_env):
    save_dir, db_, s = storage_env
    db_.set_db_version(0) # Force v0 mode
    app_id = 8888
    filename = "v0.sav"
    db_.add_new_game(app_id, "V0Game")
    s.create_game_folder("V0Game", app_id)

    t1 = datetime.datetime(2025, 1, 1, 10, 0, 0)
    t2 = datetime.datetime(2025, 1, 2, 10, 0, 0)
    t3 = datetime.datetime(2025, 1, 3, 10, 0, 0)

    # Insert versions into db with v0 version_num
    cur = db_.con.cursor()
    cur.execute("INSERT INTO FILES VALUES (NULL, ?, ?, ?);", (filename, "./", app_id))
    file_id = cur.lastrowid
    cur.execute("INSERT INTO VERSION (version_id, file_id, time, version_num) VALUES (NULL, ?, ?, ?);", (file_id, t3, 0))
    cur.execute("INSERT INTO VERSION (version_id, file_id, time, version_num) VALUES (NULL, ?, ?, ?);", (file_id, t2, 1))
    cur.execute("INSERT INTO VERSION (version_id, file_id, time, version_num) VALUES (NULL, ?, ?, ?);", (file_id, t1, 2))
    db_.con.commit()

    game_dir = os.path.join(save_dir, str(app_id))
    # Write active file and v0 .scsd_2 file
    with open(os.path.join(game_dir, filename), "w") as f:
        f.write("active")
    with open(os.path.join(game_dir, f"{filename}.scsd_1"), "w") as f:
        f.write("v2")
    with open(os.path.join(game_dir, f"{filename}.scsd_2"), "w") as f:
        f.write("v1")
    with open(os.path.join(game_dir, f"{filename}.scsd_3"), "w") as f:
        f.write("orphan_glob_target")

    # Rotation is 2, so version t1 (which had version_num 2) should be pruned
    # Additionally, the v0 glob branch should find and prune .scsd_3 despite it not being in the DB
    s.remove_outdated(app_id, filename, "./", file_id)

    assert not os.path.exists(os.path.join(game_dir, f"{filename}.scsd_3"))
    assert not os.path.exists(os.path.join(game_dir, f"{filename}.scsd_2"))
    assert os.path.isfile(os.path.join(game_dir, f"{filename}.scsd_1"))
    assert os.path.isfile(os.path.join(game_dir, filename))

def test_v0_rotate_file(storage_env):
    save_dir, db_, s = storage_env
    db_.set_db_version(0) # Force v0 mode
    app_id = 8889
    filename = "leg_rotate.sav"
    db_.add_new_game(app_id, "LegRotateGame")
    s.create_game_folder("LegRotateGame", app_id)

    cur = db_.con.cursor()
    cur.execute("INSERT INTO FILES VALUES (NULL, ?, ?, ?);", (filename, "./", app_id))
    file_id = cur.lastrowid
    db_.con.commit()

    game_dir = os.path.join(save_dir, str(app_id))
    with open(os.path.join(game_dir, filename), "w") as f:
        f.write("active")

    # Rotate file in v0 mode should rename to .scsd_1
    dt = datetime.datetime.now(datetime.timezone.utc)
    s.rotate_file(app_id, filename, "./", file_id, dt)

    assert not os.path.exists(os.path.join(game_dir, filename))
    assert os.path.isfile(os.path.join(game_dir, f"{filename}.scsd_1"))
    with open(os.path.join(game_dir, f"{filename}.scsd_1"), "r") as f:
        assert f.read() == "active"

def test_rotate_file_and_remove_outdated(storage_env):
    save_dir, db_, s = storage_env
    app_id = 9999
    filename = "game.sav"
    db_.add_new_game(app_id, "RotGame")
    s.create_game_folder("RotGame", app_id)

    t1 = datetime.datetime(2026, 1, 1, 10, 0, 0)
    t2 = datetime.datetime(2026, 1, 2, 10, 0, 0)
    t3 = datetime.datetime(2026, 1, 3, 10, 0, 0)

    # Initial file v1
    db_.add_new_files([(filename, "./", app_id, t1)])
    file_id = db_.get_file_id(app_id, "./", filename)

    active_path = s.get_filename_location(app_id, filename, "./")
    with open(active_path, "w") as f:
        f.write("version 1")

    # Rotate v1 -> v2
    s.rotate_file(app_id, filename, "./", file_id, t2, t1)
    backup_1 = s.get_filename_location(app_id, filename, "./", t1)
    assert os.path.isfile(backup_1)
    with open(backup_1, "r") as f:
        assert f.read() == "version 1"

    # Simulate downloading v2
    with open(active_path, "w") as f:
        f.write("version 2")

    # Rotate v2 -> v3
    s.rotate_file(app_id, filename, "./", file_id, t3, t2)
    backup_2 = s.get_filename_location(app_id, filename, "./", t2)
    assert os.path.isfile(backup_2)
    with open(backup_2, "r") as f:
        assert f.read() == "version 2"

    # Crucial test: backup_1 must still exist and was NOT renamed
    assert os.path.isfile(backup_1)

    # Simulate downloading v3
    with open(active_path, "w") as f:
        f.write("version 3")

    # Now remove outdated (rotation is 2, so newest 2: t3 and t2 are kept, t1 should be deleted)
    s.remove_outdated(app_id, filename, "./", file_id)

    assert not os.path.exists(backup_1)
    assert os.path.isfile(backup_2)
    assert os.path.isfile(active_path)

def test_rename_legacy_backups(storage_env):
    save_dir, db_, s = storage_env
    app_id = 7777
    filename = "slot.sav"
    db_.add_new_game(app_id, "MigrateGame")
    s.create_game_folder("MigrateGame", app_id)

    t1 = datetime.datetime(2025, 5, 1, 12, 0, 0)
    t2 = datetime.datetime(2025, 5, 2, 12, 0, 0)
    t3 = datetime.datetime(2025, 5, 3, 12, 0, 0)

    # In a v0 database, v3 is newest (version_num=0), v2 is .scsd_1, v1 is .scsd_2
    cur = db_.con.cursor()
    cur.execute("INSERT INTO FILES VALUES (NULL, ?, ?, ?);", (filename, "./", app_id))
    file_id = cur.lastrowid
    cur.execute("INSERT INTO VERSION VALUES (NULL, ?, ?, ?);", (file_id, t3, 0))
    cur.execute("INSERT INTO VERSION VALUES (NULL, ?, ?, ?);", (file_id, t2, 1))
    cur.execute("INSERT INTO VERSION VALUES (NULL, ?, ?, ?);", (file_id, t1, 2))
    db_.con.commit()

    game_dir = os.path.join(save_dir, str(app_id))
    with open(os.path.join(game_dir, filename), "w") as f:
        f.write("v3_content")
    with open(os.path.join(game_dir, f"{filename}.scsd_1"), "w") as f:
        f.write("v2_content")
    with open(os.path.join(game_dir, f"{filename}.scsd_2"), "w") as f:
        f.write("v1_content")

    # Run migration
    s.rename_legacy_backups(app_id)

    # Check that v0 files are renamed to timestamp format
    assert not os.path.exists(os.path.join(game_dir, f"{filename}.scsd_1"))
    assert not os.path.exists(os.path.join(game_dir, f"{filename}.scsd_2"))

    migrated_v2 = os.path.join(game_dir, f"{filename}.scsd_20250502_120000")
    migrated_v1 = os.path.join(game_dir, f"{filename}.scsd_20250501_120000")
    assert os.path.isfile(migrated_v2)
    assert os.path.isfile(migrated_v1)
    with open(migrated_v2, "r") as f:
        assert f.read() == "v2_content"
    with open(migrated_v1, "r") as f:
        assert f.read() == "v1_content"
    # Active file is unaffected
    assert os.path.isfile(os.path.join(game_dir, filename))
    with open(os.path.join(game_dir, filename), "r") as f:
        assert f.read() == "v3_content"

def test_migrate_orphaned_v0_backups(storage_env):
    save_dir, db_, s = storage_env
    app_id = 6666
    filename = "orphan.sav"
    db_.add_new_game(app_id, "OrphanGame")
    s.create_game_folder("OrphanGame", app_id)

    game_dir = os.path.join(save_dir, str(app_id))
    orphan_path = os.path.join(game_dir, f"{filename}.scsd_5")
    with open(orphan_path, "w") as f:
        f.write("orphaned_backup")

    # Set known mtime
    target_dt = datetime.datetime(2024, 11, 15, 8, 30, 0, tzinfo=datetime.timezone.utc)
    ts = target_dt.timestamp()
    os.utime(orphan_path, (ts, ts))

    s.rename_legacy_backups(app_id)

    assert not os.path.exists(orphan_path)
    expected_migrated = os.path.join(game_dir, f"{filename}.scsd_20241115_083000")
    assert os.path.isfile(expected_migrated)
    with open(expected_migrated, "r") as f:
        assert f.read() == "orphaned_backup"

def test_increment_file_version_v0(storage_env):
    save_dir, db_, s = storage_env
    app_id = 5555
    filename = "shift.sav"
    db_.add_new_game(app_id, "ShiftGame")
    s.create_game_folder("ShiftGame", app_id)

    game_dir = os.path.join(save_dir, str(app_id))
    with open(os.path.join(game_dir, filename), "w") as f:
        f.write("0")
    with open(os.path.join(game_dir, f"{filename}.scsd_1"), "w") as f:
        f.write("1")

    # Call increment_file_version with max_version=3
    # 0 -> 1, 1 -> 2
    s.increment_file_version(app_id, filename, "./", 3)

    assert not os.path.exists(os.path.join(game_dir, filename))
    with open(os.path.join(game_dir, f"{filename}.scsd_1"), "r") as f:
        assert f.read() == "0"
    with open(os.path.join(game_dir, f"{filename}.scsd_2"), "r") as f:
        assert f.read() == "1"
