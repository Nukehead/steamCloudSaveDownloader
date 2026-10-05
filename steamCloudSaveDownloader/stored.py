import datetime
from . import db

import logging

logger = logging.getLogger('scsd')

class stored:
    def __init__(self, staged_args, save_dir):
        self.target = staged_args
        self.save_dir = save_dir
        self.db = db.db(save_dir)

    def get_result(self):
        id_and_names = self.db.get_stored_game_names(self.target)
        for app_id, game_name in id_and_names:
            print(f"- {game_name}({app_id})")
            files_info = \
                self.db.get_files_info_by_appid(app_id)
            for file_id, filename, location in files_info:
                print(f"  - {location}/{filename}")
                version_info = \
                    self.db.get_file_version_by_file_id(file_id)
                for i, (utc_date, v_num) in enumerate(version_info):
                    if utc_date is not None:
                        aware_utc = utc_date.replace(tzinfo=datetime.timezone.utc)
                        local_date = aware_utc.astimezone().replace(tzinfo=None)
                    else:
                        local_date = None
                    if i == 0:
                        suffix_text = "(active)"
                    elif v_num is not None and v_num > 0:
                        suffix_text = f"(backup: .scsd_{v_num})"
                    else:
                        suffix_str = utc_date.strftime("%Y%m%d_%H%M%S") if utc_date else "unknown"
                        suffix_text = f"(backup: .scsd_{suffix_str})"

                    print(f"    - {local_date} {suffix_text}")
