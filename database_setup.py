import sqlite3

# Create database file
conn = sqlite3.connect("anime.db")
cursor = conn.cursor()

# ======================
# Create Tables
# ======================

cursor.execute("""
CREATE TABLE IF NOT EXISTS animes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id INTEGER,
    episode_number INTEGER,
    file_id TEXT,
    UNIQUE(anime_id, episode_number),
    FOREIGN KEY (anime_id) REFERENCES animes (id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,
    total_requests INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS watch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    anime_id INTEGER,
    episode_number INTEGER,
    watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================
# Performance Indexes
# ======================

cursor.execute("CREATE INDEX IF NOT EXISTS idx_anime_name ON animes(name)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_episode_lookup ON episodes(anime_id, episode_number)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_episode_anime ON episodes(anime_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_watch_user ON watch_history(user_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_watch_anime ON watch_history(anime_id)")

# ======================
# Commit & Close
# ======================

conn.commit()
conn.close()

print("Database created successfully.")