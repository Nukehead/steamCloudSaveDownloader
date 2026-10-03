import sqlite3

def seed_game(db_, app_id, name, dir_name):
    cur = db_.con.cursor()
    cur.execute("INSERT INTO GAMES VALUES (?, ?, ?);", (app_id, name, dir_name))
    db_.con.commit()

def seed_file(db_, filename, path, app_id):
    cur = db_.con.cursor()
    cur.execute("INSERT INTO FILES VALUES (NULL, ?, ?, ?);", (filename, path, app_id))
    db_.con.commit()
    return cur.lastrowid

def seed_version(db_, file_id, time, version_num):
    cur = db_.con.cursor()
    cur.execute("INSERT INTO VERSION (version_id, file_id, time, version_num) VALUES (NULL, ?, ?, ?);", (file_id, time, version_num))
    db_.con.commit()
    return cur.lastrowid
