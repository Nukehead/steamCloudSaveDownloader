"""
Database and Filesystem Migration Orchestrator

Migration Philosophy:
Migrations are classified as either Mandatory or Optional.
- Mandatory migrations resolve structural or critical data issues (e.g., timezone fixes)
  and are executed automatically during normal application startup.
- Optional migrations perform non-critical adjustments (e.g., renaming files on disk)
  and must be explicitly triggered by the user via the `--migrate` CLI flag.

Rule: Optional migrations are ONLY allowed at the end of the version tree.
There can never be an optional migration preceding a mandatory one. If a future
migration requires bumping the mandatory boundary (MINIMUM_DB_VERSION), all preceding
optional migrations are implicitly forced to become mandatory.
"""

import logging
import datetime
from zoneinfo import ZoneInfo
from . import db

logger = logging.getLogger('scsd')

class DatabaseMigrator:
    def __init__(self, db_, storage_):
        self.db_ = db_
        self.storage_ = storage_

    def run(self, manual=False):
        current_version = self.db_.get_db_version()
        target_version = db.db.LATEST_DB_VERSION

        if current_version == target_version:
            return

        if current_version == 0:
            logger.info("Migrating from database version 0 to 1...")
            logger.info("  Correcting legacy Pacific Time timestamps to true UTC...")
            self._migrate_v0_to_v1()
            self.db_.set_db_version(1)
            current_version = 1
            logger.info("Migration to v1 complete.")

        if current_version == 1:
            if manual:
                logger.info("Migrating from database version 1 to 2...")
                logger.info("  Changing local file name from numbered suffix to timestamped suffix (i.e. .scsd_1 to .scsd_20260904_231455)...")
                game_list = self.db_.get_stored_game_names([])
                for app_id, game_name in game_list:
                    logger.info(f"    Migrating {game_name} ({app_id})...")
                    self.storage_.rename_legacy_backups(app_id)

                self.db_.set_db_version(2)
                current_version = 2
                logger.info("Migration to v2 complete.")
            else:
                # Do not log or attempt v1->v2 without the manual flag
                pass


    def _migrate_v0_to_v1(self):
        cur = self.db_.con.cursor()
        res = cur.execute("SELECT file_id, version_num, time FROM VERSION;")
        rows = res.fetchall()

        steam_tz = ZoneInfo("America/Los_Angeles")

        for file_id, version_num, legacy_time in rows:
            if legacy_time is None:
                continue

            if isinstance(legacy_time, str):
                try:
                    legacy_time = datetime.datetime.fromisoformat(legacy_time)
                except ValueError:
                    legacy_time = datetime.datetime.strptime(legacy_time.split(".")[0], "%Y-%m-%d %H:%M:%S")

            if legacy_time.tzinfo is None:
                utc_time = legacy_time.replace(tzinfo=steam_tz).astimezone(datetime.timezone.utc)
            else:
                # If somehow already timezone aware, shift from PST
                utc_time = legacy_time.replace(tzinfo=steam_tz).astimezone(datetime.timezone.utc)

            # Standardize as naive UTC to match how scsd natively inserts new files
            naive_utc_time = utc_time.replace(tzinfo=None)

            cur.execute(
                "UPDATE VERSION SET time = ? WHERE file_id = ? AND version_num = ?",
                (naive_utc_time, file_id, version_num)
            )
        self.db_.con.commit()
