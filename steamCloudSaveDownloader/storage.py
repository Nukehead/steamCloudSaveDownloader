import os
import pathlib
from . import db
from . import err
from .err import err_enum
import datetime
import logging
import signal
import glob
import typing

logger = logging.getLogger('scsd')

class keyboard_interrupt_handler:
    def __enter__(self):
        self.signal_received = False
        self.old_handler = signal.signal(signal.SIGINT, self.handler)

    def handler(self, sig, frame):
        self.signal_received = (sig, frame)
        logger.warning('SIGINT received. Delaying to ensure consistency.')

    def __exit__(self, type, value, traceback):
        signal.signal(signal.SIGINT, self.old_handler)
        if self.signal_received:
            self.old_handler(*self.signal_received)

def key_interrupt_atomic(func):
    def wrapper(*args, **kwargs):
        with keyboard_interrupt_handler():
            retval = func(*args, **kwargs)
        return retval
    return wrapper

class storage:
    s_version_prefix = '.scsd_'

    def __init__(self, location:str, db_:db.db):
        self.location = location
        self.db_ = db_

    def create_game_folder(self, game_name:str, app_id:int):
        db_game_dir = self.db_.get_game_dir(app_id)

        if (db_game_dir is not None):
            if os.path.isdir(os.path.join(self.location, db_game_dir)):
                return
            else:
                dir_name = db_game_dir
        else:
            dir_name = f"{app_id}"

        target_dir = os.path.join(self.location, dir_name)

        if os.path.isdir(target_dir):
            return

        try:
            os.mkdir(target_dir)
        except:
            pass

        if os.path.isdir(target_dir):
            self.db_.set_game_dir(app_id, dir_name)
            return

        # Maybe game_name contains special character fallback to app_id
        dir_name = f"{app_id}__"
        target_dir = os.path.join(self.location, dir_name)

        if os.path.isdir(target_dir):
            return

        try:
            self.db_.set_game_dir(app_id, dir_name)
            os.mkdir(target_dir)
        except:
            raise err.err(err_enum.CANNOT_CREATE_DIRECTORY)

    @staticmethod
    def format_version_time(version_time: datetime.datetime) -> str:
        """All timestamps in the database and file suffixes represent UTC."""
        return version_time.strftime("%Y%m%d_%H%M%S")

    def get_version_suffix(self, version_time: "typing.Union[int, str, datetime.datetime, None]" = None) -> str:
        """
        Generates the appropriate file suffix based on the provided type:
        - None / 0: Active file (no suffix)
        - int: Legacy v0 backup suffix (e.g. .scsd_1)
        - datetime (or ISO str): v1 timestamp suffix (e.g. .scsd_20260904_231455)
        """
        if version_time is None or version_time == 0:
            return ""
        if isinstance(version_time, int):
            return f"{storage.s_version_prefix}{version_time}"
        if isinstance(version_time, str):
            try:
                version_time = datetime.datetime.fromisoformat(version_time)
            except ValueError:
                return f"{storage.s_version_prefix}{version_time}"
        if isinstance(version_time, datetime.datetime):
            return f"{storage.s_version_prefix}{storage.format_version_time(version_time)}"
        return f"{storage.s_version_prefix}{version_time}"

    # Implicitly create the path if not exist
    def get_filename_location(self,
                              app_id:int,
                              filename:str,
                              file_path:str,
                              version_time=None):
        db_game_dir = self.db_.get_game_dir(app_id)

        version_suffix = self.get_version_suffix(version_time)

        path_to_save = os.path.join(self.location, db_game_dir, file_path)

        os.makedirs(path_to_save, exist_ok=True)

        return os.path.join(path_to_save, filename + version_suffix)

    @key_interrupt_atomic
    def increment_file_version(self,
                               app_id:int,
                               filename:str,
                               file_path:str,
                               current_max_version:int):
        db_game_dir = self.db_.get_game_dir(app_id)
        path_to_save = os.path.join(self.location, db_game_dir, file_path)

        for old, new in zip(
                range(current_max_version - 2, -1, -1),
                range(current_max_version - 1, 0, -1)):
            old_version_suffix = self.get_version_suffix(old)
            new_version_suffix = self.get_version_suffix(new)

            old_name = os.path.join(path_to_save, filename + old_version_suffix)
            new_name = os.path.join(path_to_save, filename + new_version_suffix)

            if os.path.exists(old_name):
                old_file_info = os.stat(old_name)
                old_mtime = old_file_info.st_mtime
                os.replace(old_name, new_name)
                os.utime(new_name, (old_mtime, old_mtime))

    @key_interrupt_atomic
    def rename_legacy_backups(self, app_id: int):
        db_game_dir = self.db_.get_game_dir(app_id)
        if db_game_dir is None:
            return

        game_dir_path = os.path.join(self.location, db_game_dir)
        if not os.path.isdir(game_dir_path):
            return

        files_info = self.db_.get_files_info_by_appid(app_id)
        for file_id, filename, rel_path in files_info:
            path_to_save = os.path.join(self.location, db_game_dir, rel_path)
            if not os.path.isdir(path_to_save):
                continue

            versions = self.db_.get_file_version_by_file_id(file_id)
            for v_time, v_num in versions:
                if v_num == 0:
                    # Skip the active file (version 0), as it has no suffix to rename
                    continue
                try:
                    legacy_file = os.path.join(path_to_save, f"{filename}.scsd_{v_num}")
                    if os.path.isfile(legacy_file):
                        new_suffix = self.get_version_suffix(v_time)
                        new_file = os.path.join(path_to_save, filename + new_suffix)
                        if not os.path.exists(new_file):
                            old_info = os.stat(legacy_file)
                            os.replace(legacy_file, new_file)
                            os.utime(new_file, (old_info.st_mtime, old_info.st_mtime))
                            logger.info(f"Migrated legacy backup '{legacy_file}' -> '{new_file}'")
                        else:
                            try:
                                os.remove(legacy_file)
                            except OSError:
                                pass
                except OSError as e:
                    logger.warning(f"Failed to migrate legacy backup for {filename}: {e}")

        # Also scan the entire game folder for any remaining legacy .scsd_<digits> files
        try:
            for root, _, filenames in os.walk(game_dir_path):
                for entry in filenames:
                    idx = entry.find(storage.s_version_prefix)
                    if idx != -1:
                        suffix_part = entry[idx + len(storage.s_version_prefix):]
                        if suffix_part.isdigit():
                            v0_orphan = os.path.join(root, entry)
                            base_name = entry[:idx]
                            old_info = os.stat(v0_orphan)
                            mtime = old_info.st_mtime
                            orphan_dt = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
                            orphan_target = os.path.join(root, base_name + self.get_version_suffix(orphan_dt))
                            if not os.path.exists(orphan_target):
                                os.replace(v0_orphan, orphan_target)
                                os.utime(orphan_target, (mtime, mtime))
                                logger.info(f"Migrated orphaned v0 backup '{v0_orphan}' -> '{orphan_target}'")
                            else:
                                try:
                                    os.remove(v0_orphan)
                                except OSError:
                                    pass
        except OSError:
            pass

    @property
    def is_timestamp_mode(self):
        return self.db_.get_db_version() >= 1

    @key_interrupt_atomic
    def rotate_file(self,
                    app_id:int,
                    filename:str,
                    file_path:str,
                    file_id:int,
                    newest_file_time: datetime.datetime,
                    current_file_time: datetime.datetime = None):
        db_game_dir = self.db_.get_game_dir(app_id)
        path_to_save = os.path.join(self.location, db_game_dir, file_path)

        if current_file_time is None:
            current_file_time = self.db_.get_latest_file_version_time(file_id)

        current_file = os.path.join(path_to_save, filename)

        if self.is_timestamp_mode:
            if current_file_time is not None and os.path.isfile(current_file):
                archive_suffix = self.get_version_suffix(current_file_time)
                archive_file = os.path.join(path_to_save, filename + archive_suffix)

                old_file_info = os.stat(current_file)
                old_mtime = old_file_info.st_mtime
                os.replace(current_file, archive_file)
                os.utime(archive_file, (old_mtime, old_mtime))
        else:
            # TODO: Remove v0 rotation logic once MINIMUM_DB_VERSION > 0
            if os.path.isfile(current_file):
                self.increment_file_version(app_id, filename, file_path, self.db_.rotation)

        self.db_.update_file_update_time_to_now(file_id, newest_file_time)

    @key_interrupt_atomic
    def remove_outdated(self,
                        app_id:int,
                        filename:str,
                        file_path:str,
                        file_id:int):
        db_game_dir = self.db_.get_game_dir(app_id)
        path_to_save = os.path.join(self.location, db_game_dir, file_path)

        if self.is_timestamp_mode:
            outdated_versions = self.db_.remove_outdated_file(file_id)
            if not outdated_versions:
                return

            for version_time, v0_version_num in outdated_versions:

                version_suffix = self.get_version_suffix(version_time)
                target = os.path.join(path_to_save, filename + version_suffix)
                logger.info(f"Remove rotated file {filename + version_suffix}")
                try:
                    if os.path.exists(target):
                        os.remove(target)
                    elif v0_version_num is not None:
                        v0_suffix = self.get_version_suffix(v0_version_num)
                        v0_target = os.path.join(path_to_save, filename + v0_suffix)
                        if os.path.exists(v0_target):
                            os.remove(v0_target)
                except OSError:
                    e = err.err(err_enum.CANNOT_REMOVE_OUTDATED)
                    e.set_additional_info(filename + version_suffix)
                    e.log()
        else:
            # TODO: Remove v0 rotation logic once MINIMUM_DB_VERSION > 0
            rotation = self.db_.rotation
            if rotation <= 0:
                return
            pattern = os.path.join(path_to_save, f"{filename}.scsd_*")
            for f in glob.glob(pattern):
                try:
                    suffix_str = f.split('.scsd_')[-1]
                    if suffix_str.isdigit() and int(suffix_str) >= rotation:
                        os.remove(f)
                except OSError:
                    pass
