import sqlite3

DB_NAME = "reviews.db"


def init_all_dbs():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS markers
                 (
                     id
                     INTEGER
                     PRIMARY
                     KEY
                     AUTOINCREMENT,
                     lat
                     REAL,
                     lon
                     REAL,
                     category
                     TEXT,
                     description
                     TEXT,
                     user
                     TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS reviews
    (
        id
        INTEGER
        PRIMARY
        KEY
        AUTOINCREMENT,
        marker_id
        INTEGER,
        reviewer
        TEXT,
        vote
        INTEGER,
        comment
        TEXT,
        FOREIGN
        KEY
                 (
        marker_id
                 ) REFERENCES markers
                 (
                     id
                 ))''')
    conn.commit()
    conn.close()


def save_marker(lat, lon, category, description, user):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO markers (lat, lon, category, description, user) VALUES (?, ?, ?, ?, ?)",
              (lat, lon, category, description, user))
    conn.commit()
    conn.close()


def get_all_markers():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT lat, lon, category, description FROM markers")
    data = c.fetchall()
    conn.close()
    return data


def get_user_stats(username):
    init_all_dbs()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('''SELECT IFNULL(SUM(reviews.vote), 0)
                 FROM reviews
                          JOIN markers ON reviews.marker_id = markers.id
                 WHERE markers.user = ?''', (username,))
    rating = c.fetchone()[0] or 0

    c.execute('''SELECT reviews.reviewer, reviews.comment, markers.category, reviews.vote
                 FROM reviews
                          JOIN markers ON reviews.marker_id = markers.id
                 WHERE markers.user = ?''', (username,))
    reviews = c.fetchall()

    conn.close()
    return rating, reviews
