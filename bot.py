CHANNEL_ID = -1003819722036
ADMIN_ID = 6374990539

# ================================
# 🔥 FORCE JOIN SETTINGS
# ================================
FORCE_JOIN_CHANNEL = "@farrisforger"
FORCE_JOIN_LINK = "https://t.me/farrisforger"



from telegram.ext import MessageHandler, filters
from psycopg2 import pool

import psycopg2
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ANIME_PER_PAGE = 10
EPISODES_PER_PAGE = 50
EPISODES_PER_COLUMN = 10

user_cooldown = {}

# =====================================================
# ========== CONNECTION POOL ==========================
# =====================================================

connection_pool = None

def init_pool():
    global connection_pool
    connection_pool = pool.SimpleConnectionPool(
        minconn=2,
        maxconn=10,
        dsn=DATABASE_URL,
        sslmode='require'
    )
    print("✅ Connection pool initialized.")

def get_conn():
    return connection_pool.getconn()

def release_conn(conn):
    connection_pool.putconn(conn)

# =====================================================
# ========== DATABASE INIT ============================
# =====================================================

def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_requests INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS animes (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seasons (
            id SERIAL PRIMARY KEY,
            anime_id INTEGER REFERENCES animes(id),
            season_number INTEGER NOT NULL,
            UNIQUE(anime_id, season_number)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id SERIAL PRIMARY KEY,
            anime_id INTEGER REFERENCES animes(id),
            season_id INTEGER,
            episode_number INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            UNIQUE(anime_id, episode_number)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watch_history (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            anime_id INTEGER,
            season_id INTEGER,
            episode_number INTEGER,
            watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cursor.close()
    release_conn(conn)
    print("✅ Database tables initialized.")

# =====================================================
# ========== ANTI SPAM ================================
# =====================================================

def is_spamming(user_id):
    now = asyncio.get_event_loop().time()
    if user_id in user_cooldown:
        if now - user_cooldown[user_id] < 2:
            return True
    user_cooldown[user_id] = now
    return False

# =====================================================
# ========== FORCE JOIN CHECK =========================
# =====================================================

async def is_user_member(bot, user_id):
    try:
        member = await bot.get_chat_member(chat_id=FORCE_JOIN_CHANNEL, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

async def send_join_message(update):
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=FORCE_JOIN_LINK)],
        [InlineKeyboardButton("✅ I Joined!", callback_data="check_join")]
    ]
    await update.message.reply_text(
        "⚠️ You must join our channel first to use this bot!\n\n"
        "👇 Click the button below to join:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =====================================================
# ========== EPISODE GRID LAYOUT ======================
# =====================================================

def build_episode_keyboard(episodes, season_id, anime_id, page=0):
    start = page * EPISODES_PER_PAGE
    end = start + EPISODES_PER_PAGE
    page_episodes = episodes[start:end]

    keyboard = []
    columns = []
    for i in range(0, len(page_episodes), EPISODES_PER_COLUMN):
        columns.append(page_episodes[i:i + EPISODES_PER_COLUMN])

    if len(columns) > 1:
        header_row = []
        for col_idx in range(len(columns)):
            col_start = start + col_idx * EPISODES_PER_COLUMN + 1
            col_end = min(start + (col_idx + 1) * EPISODES_PER_COLUMN, start + len(page_episodes))
            header_row.append(
                InlineKeyboardButton(f"Ep {col_start}-{col_end}", callback_data="noop")
            )
        keyboard.append(header_row)

    max_rows = max(len(col) for col in columns) if columns else 0
    for row in range(max_rows):
        ep_row = []
        for col in columns:
            if row < len(col):
                ep = col[row]
                ep_row.append(
                    InlineKeyboardButton(
                        f"Ep {ep[0]}",
                        callback_data=f"episode|{anime_id}|{season_id}|{ep[0]}"
                    )
                )
            else:
                # Empty placeholder to keep grid structure
                ep_row.append(
                    InlineKeyboardButton(" ", callback_data="noop")
                )
        if ep_row:
            keyboard.append(ep_row)

    nav = []
    total_episodes = len(episodes)
    if page > 0:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"eppage|{anime_id}|{season_id}|{page-1}"))
    if end < total_episodes:
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"eppage|{anime_id}|{season_id}|{page+1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔙 Back to Seasons", callback_data=f"seasons|{anime_id}")])
    return keyboard

# =====================================================
# ========== BOT HANDLERS =============================
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await is_user_member(context.bot, user_id):
        await send_join_message(update)
        return

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, last_active, total_requests)
        VALUES (%s, CURRENT_TIMESTAMP, 1)
        ON CONFLICT (user_id)
        DO UPDATE SET
            last_active = CURRENT_TIMESTAMP,
            total_requests = users.total_requests + 1
    """, (user_id,))
    conn.commit()
    cursor.close()
    release_conn(conn)

    keyboard = [[InlineKeyboardButton("📚 Browse Anime", callback_data="show_anime")]]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])

    await update.message.reply_text(
        "Welcome! Choose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def check_join(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not await is_user_member(context.bot, user_id):
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=FORCE_JOIN_LINK)],
            [InlineKeyboardButton("✅ I Joined!", callback_data="check_join")]
        ]
        await query.edit_message_text(
            "❌ You have not joined the channel yet!\n\nPlease join and then click 'I Joined!' again:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, last_active, total_requests)
        VALUES (%s, CURRENT_TIMESTAMP, 1)
        ON CONFLICT (user_id)
        DO UPDATE SET
            last_active = CURRENT_TIMESTAMP,
            total_requests = users.total_requests + 1
    """, (user_id,))
    conn.commit()
    cursor.close()
    release_conn(conn)

    keyboard = [[InlineKeyboardButton("📚 Browse Anime", callback_data="show_anime")]]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])

    await query.edit_message_text(
        "✅ Thank you for joining! Welcome!\n\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_anime(update, context):
    query = update.callback_query
    await query.answer()

    page = 0
    if query.data.startswith("page|"):
        page = int(query.data.split("|")[1])

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM animes")
    total = cursor.fetchone()[0]
    cursor.execute("""
        SELECT name FROM animes ORDER BY name ASC LIMIT %s OFFSET %s
    """, (ANIME_PER_PAGE, page * ANIME_PER_PAGE))
    animes = cursor.fetchall()
    cursor.close()
    release_conn(conn)

    keyboard = [[InlineKeyboardButton("🔍 Search", callback_data="search_mode")]]
    for anime in animes:
        keyboard.append([InlineKeyboardButton(anime[0], callback_data=f"anime|{anime[0]}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅ Previous", callback_data=f"page|{page-1}"))
    if (page + 1) * ANIME_PER_PAGE < total:
        nav_buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"page|{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    await query.edit_message_text("Select an anime:", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_seasons(update, context):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("anime|"):
        _, anime_name = query.data.split("|", 1)
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
        result = cursor.fetchone()
        if not result:
            await query.answer("Anime not found!", show_alert=True)
            cursor.close()
            release_conn(conn)
            return
        anime_id = result[0]
        cursor.close()
        release_conn(conn)
    else:
        _, anime_id = query.data.split("|", 1)
        anime_id = int(anime_id)

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM animes WHERE id = %s", (anime_id,))
    anime_name = cursor.fetchone()[0]
    cursor.execute("""
        SELECT id, season_number FROM seasons
        WHERE anime_id = %s ORDER BY season_number ASC
    """, (anime_id,))
    seasons = cursor.fetchall()
    cursor.close()
    release_conn(conn)

    if not seasons:
        await query.edit_message_text(
            f"❌ No seasons found for {anime_name}.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="show_anime")]
            ])
        )
        return

    keyboard = []
    for season in seasons:
        season_id, season_number = season
        keyboard.append([
            InlineKeyboardButton(
                f"🎬 Season {season_number}",
                callback_data=f"season_ep|{anime_id}|{season_id}|0"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="show_anime")])

    await query.edit_message_text(
        f"📺 {anime_name}\n\nSelect a season:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_episodes(update, context):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    anime_id = int(parts[1])
    season_id = int(parts[2])
    page = int(parts[3])

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM animes WHERE id = %s", (anime_id,))
    anime_name = cursor.fetchone()[0]
    cursor.execute("SELECT season_number FROM seasons WHERE id = %s", (season_id,))
    season_number = cursor.fetchone()[0]
    cursor.execute("""
        SELECT episode_number FROM episodes
        WHERE season_id = %s ORDER BY episode_number ASC
    """, (season_id,))
    episodes = cursor.fetchall()
    cursor.close()
    release_conn(conn)

    if not episodes:
        await query.edit_message_text(
            f"❌ No episodes found for Season {season_number}.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data=f"seasons|{anime_id}")]
            ])
        )
        return

    keyboard = build_episode_keyboard(episodes, season_id, anime_id, page)
    total = len(episodes)
    start = page * EPISODES_PER_PAGE + 1
    end = min((page + 1) * EPISODES_PER_PAGE, total)

    await query.edit_message_text(
        f"📺 {anime_name} — Season {season_number}\n🎬 Episodes {start}-{end} of {total}:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def send_episode(update, context):
    query = update.callback_query
    await query.answer()

    if is_spamming(query.from_user.id):
        await query.answer("Please slow down 😄", show_alert=True)
        return

    _, anime_id, season_id, episode_number = query.data.split("|")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT file_id FROM episodes
        WHERE season_id = %s AND episode_number = %s
    """, (season_id, episode_number))
    result = cursor.fetchone()

    if not result:
        await query.answer("Episode not found!", show_alert=True)
        cursor.close()
        release_conn(conn)
        return

    file_id = result[0]
    cursor.execute("SELECT season_number FROM seasons WHERE id = %s", (season_id,))
    season_number = cursor.fetchone()[0]

    video_msg = await query.message.reply_video(
        video=file_id,
        caption=f"Season {season_number} — Episode {episode_number}"
    )

    cursor.execute("""
        INSERT INTO watch_history (user_id, anime_id, season_id, episode_number)
        VALUES (%s, %s, %s, %s)
    """, (query.from_user.id, anime_id, season_id, episode_number))
    conn.commit()
    cursor.close()
    release_conn(conn)

    warning_msg = await query.message.reply_text("⚠️ All messages will be deleted in 5 minutes.")
    asyncio.create_task(auto_delete([video_msg, warning_msg, query.message]))


async def handle_channel_video(update, context):
    print("Channel update received")

    if update.channel_post and update.channel_post.video:
        print("Video detected in channel")
        file_id = update.channel_post.video.file_id
        caption = update.channel_post.caption
        print("Caption:", caption)

        if not caption:
            print("No caption found")
            return

        parts = caption.split("|")
        if len(parts) != 3:
            print("Caption format incorrect. Use: Anime Name | Season | Episode")
            return

        anime_name = parts[0].strip()
        season_number = int(parts[1].strip())
        episode_number = int(parts[2].strip())

        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
        result = cursor.fetchone()
        if not result:
            print(f"Anime '{anime_name}' not found")
            cursor.close()
            release_conn(conn)
            return

        anime_id = result[0]

        cursor.execute("""
            INSERT INTO seasons (anime_id, season_number)
            VALUES (%s, %s) ON CONFLICT (anime_id, season_number) DO NOTHING
        """, (anime_id, season_number))

        cursor.execute("SELECT id FROM seasons WHERE anime_id = %s AND season_number = %s", (anime_id, season_number))
        season_id = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO episodes (anime_id, season_id, episode_number, file_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (anime_id, episode_number)
            DO UPDATE SET file_id = EXCLUDED.file_id, season_id = EXCLUDED.season_id
        """, (anime_id, season_id, episode_number, file_id))

        conn.commit()
        cursor.close()
        release_conn(conn)
        print(f"✅ {anime_name} | Season {season_number} | Episode {episode_number} saved.")


async def auto_delete(messages):
    await asyncio.sleep(300)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass


async def add_anime(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /add_anime Anime Name")
        return
    anime_name = " ".join(context.args)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO animes (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (anime_name,))
    conn.commit()
    cursor.close()
    release_conn(conn)
    await update.message.reply_text(f"✅ {anime_name} added successfully.")



async def bulk_add(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /bulk_add Anime Name | Season Number | StartEpisode-EndEpisode
"
            "Example: /bulk_add Naruto | 1 | 1-24"
        )
        return

    text = " ".join(context.args)
    parts = text.split("|")
    if len(parts) != 3:
        await update.message.reply_text(
            "Usage: /bulk_add Anime Name | Season Number | StartEpisode-EndEpisode
"
            "Example: /bulk_add Naruto | 1 | 1-24"
        )
        return

    anime_name = parts[0].strip()
    season_number = int(parts[1].strip())
    episode_range = parts[2].strip()

    if "-" not in episode_range:
        await update.message.reply_text("Episode range must be like: 1-24")
        return

    start_ep, end_ep = episode_range.split("-")
    start_ep = int(start_ep.strip())
    end_ep = int(end_ep.strip())

    if start_ep > end_ep:
        await update.message.reply_text("Start episode must be less than end episode.")
        return

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
    result = cursor.fetchone()
    if not result:
        await update.message.reply_text(f"Anime '{anime_name}' not found. Add it first with /add_anime")
        cursor.close()
        release_conn(conn)
        return

    anime_id = result[0]

    # Auto create season if not exists
    cursor.execute("""
        INSERT INTO seasons (anime_id, season_number)
        VALUES (%s, %s) ON CONFLICT (anime_id, season_number) DO NOTHING
    """, (anime_id, season_number))

    cursor.execute("SELECT id FROM seasons WHERE anime_id = %s AND season_number = %s", (anime_id, season_number))
    season_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    release_conn(conn)

    # Build the caption list for user to upload
    total = end_ep - start_ep + 1
    captions = []
    for ep in range(start_ep, end_ep + 1):
        captions.append(f"{anime_name} | {season_number} | {ep}")

    caption_text = "
".join(captions)

    await update.message.reply_text(
        f"✅ Season {season_number} ready for {anime_name}!

"
        f"Now upload {total} videos to your storage channel with these captions in order:

"
        f"{caption_text}"
    )

async def add_season(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /add_season Anime Name | Season Number")
        return
    text = " ".join(context.args)
    parts = text.split("|")
    if len(parts) != 2:
        await update.message.reply_text("Usage: /add_season Anime Name | Season Number")
        return
    anime_name = parts[0].strip()
    season_number = int(parts[1].strip())
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
    result = cursor.fetchone()
    if not result:
        await update.message.reply_text(f"Anime '{anime_name}' not found.")
        cursor.close()
        release_conn(conn)
        return
    anime_id = result[0]
    cursor.execute("""
        INSERT INTO seasons (anime_id, season_number)
        VALUES (%s, %s) ON CONFLICT (anime_id, season_number) DO NOTHING
    """, (anime_id, season_number))
    conn.commit()
    cursor.close()
    release_conn(conn)
    await update.message.reply_text(f"✅ Season {season_number} added to {anime_name}.")


async def add_episode(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /add_episode Anime Name | Season Number | Episode Number")
        return
    text = " ".join(context.args)
    parts = text.split("|")
    if len(parts) != 3:
        await update.message.reply_text("Usage: /add_episode Anime Name | Season Number | Episode Number")
        return
    anime_name = parts[0].strip()
    season_number = int(parts[1].strip())
    episode_number = int(parts[2].strip())
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
    result = cursor.fetchone()
    cursor.close()
    release_conn(conn)
    if not result:
        await update.message.reply_text("Anime not found.")
        return
    await update.message.reply_text(
        f"Now upload the episode video to the storage channel with caption:\n\n"
        f"{anime_name} | {season_number} | {episode_number}"
    )


async def delete_episode(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /delete_episode Anime Name | Season Number | Episode Number")
        return
    text = " ".join(context.args)
    parts = text.split("|")
    if len(parts) != 3:
        await update.message.reply_text("Usage: /delete_episode Anime Name | Season Number | Episode Number")
        return
    anime_name = parts[0].strip()
    season_number = int(parts[1].strip())
    episode_number = int(parts[2].strip())
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
    result = cursor.fetchone()
    if not result:
        await update.message.reply_text("Anime not found.")
        cursor.close()
        release_conn(conn)
        return
    anime_id = result[0]
    cursor.execute("SELECT id FROM seasons WHERE anime_id = %s AND season_number = %s", (anime_id, season_number))
    result = cursor.fetchone()
    if not result:
        await update.message.reply_text("Season not found.")
        cursor.close()
        release_conn(conn)
        return
    season_id = result[0]
    cursor.execute("DELETE FROM episodes WHERE season_id = %s AND episode_number = %s", (season_id, episode_number))
    conn.commit()
    cursor.close()
    release_conn(conn)
    await update.message.reply_text(f"✅ Episode {episode_number} of Season {season_number} deleted.")


async def delete_season(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /delete_season Anime Name | Season Number")
        return
    text = " ".join(context.args)
    parts = text.split("|")
    if len(parts) != 2:
        await update.message.reply_text("Usage: /delete_season Anime Name | Season Number")
        return
    anime_name = parts[0].strip()
    season_number = int(parts[1].strip())
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
    result = cursor.fetchone()
    if not result:
        await update.message.reply_text("Anime not found.")
        cursor.close()
        release_conn(conn)
        return
    anime_id = result[0]
    cursor.execute("SELECT id FROM seasons WHERE anime_id = %s AND season_number = %s", (anime_id, season_number))
    result = cursor.fetchone()
    if not result:
        await update.message.reply_text("Season not found.")
        cursor.close()
        release_conn(conn)
        return
    season_id = result[0]
    cursor.execute("DELETE FROM episodes WHERE season_id = %s", (season_id,))
    cursor.execute("DELETE FROM seasons WHERE id = %s", (season_id,))
    conn.commit()
    cursor.close()
    release_conn(conn)
    await update.message.reply_text(f"✅ Season {season_number} and all its episodes deleted.")


async def delete_anime(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /delete_anime Anime Name")
        return
    anime_name = " ".join(context.args)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
    result = cursor.fetchone()
    if not result:
        await update.message.reply_text("Anime not found.")
        cursor.close()
        release_conn(conn)
        return
    anime_id = result[0]
    cursor.execute("SELECT id FROM seasons WHERE anime_id = %s", (anime_id,))
    seasons = cursor.fetchall()
    for s in seasons:
        cursor.execute("DELETE FROM episodes WHERE season_id = %s", (s[0],))
    cursor.execute("DELETE FROM seasons WHERE anime_id = %s", (anime_id,))
    cursor.execute("DELETE FROM animes WHERE id = %s", (anime_id,))
    conn.commit()
    cursor.close()
    release_conn(conn)
    await update.message.reply_text(f"✅ {anime_name} and all its seasons/episodes deleted.")


async def search_anime(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /search keyword")
        return
    keyword = " ".join(context.args)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM animes WHERE LOWER(name) LIKE LOWER(%s) ORDER BY name ASC
    """, (f"%{keyword}%",))
    results = cursor.fetchall()
    cursor.close()
    release_conn(conn)
    if not results:
        await update.message.reply_text("No anime found.")
        return
    keyboard = []
    for anime in results:
        keyboard.append([InlineKeyboardButton(anime[0], callback_data=f"anime|{anime[0]}")])
    await update.message.reply_text("Search Results:", reply_markup=InlineKeyboardMarkup(keyboard))


user_search_mode = set()


async def enter_search_mode(update, context):
    query = update.callback_query
    await query.answer()
    user_search_mode.add(query.from_user.id)
    await query.message.reply_text("Type the anime name you want to search:")


admin_state = {}


async def admin_panel(update, context):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton("➕ Add Anime", callback_data="admin_add_anime")],
        [InlineKeyboardButton("➕ Add Season", callback_data="admin_add_season")],
        [InlineKeyboardButton("➕ Add Episode", callback_data="admin_add_episode")],
        [InlineKeyboardButton("⚡ Bulk Add Episodes", callback_data="admin_bulk_add")],
        [InlineKeyboardButton("❌ Delete Anime", callback_data="admin_delete_anime")],
        [InlineKeyboardButton("❌ Delete Season", callback_data="admin_delete_season")],
        [InlineKeyboardButton("❌ Delete Episode", callback_data="admin_delete_episode")],
        [InlineKeyboardButton("📊 Analytics", callback_data="admin_analytics")],
        [InlineKeyboardButton("🔙 Back", callback_data="show_anime")]
    ]
    await query.edit_message_text("🛠 Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_admin_actions(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    action = query.data
    admin_state[user_id] = action
    if action == "admin_add_anime":
        await query.message.reply_text("Send anime name to add:")
    elif action == "admin_add_season":
        await query.message.reply_text("Send: Anime Name | Season Number\nExample: Naruto | 2")
    elif action == "admin_add_episode":
        await query.message.reply_text("Send: Anime Name | Season Number | Episode Number\nExample: Naruto | 1 | 5")
    elif action == "admin_bulk_add":
        await query.message.reply_text(
            "Send: Anime Name | Season Number | StartEpisode-EndEpisode
"
            "Example: Naruto | 1 | 1-24"
        )
    elif action == "admin_delete_anime":
        await query.message.reply_text("Send anime name to delete:")
    elif action == "admin_delete_season":
        await query.message.reply_text("Send: Anime Name | Season Number")
    elif action == "admin_delete_episode":
        await query.message.reply_text("Send: Anime Name | Season Number | Episode Number")


async def handle_admin_text(update, context):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if user_id not in admin_state:
        return
    action = admin_state[user_id]
    text = update.message.text.strip()
    conn = get_conn()
    cursor = conn.cursor()

    if action == "admin_add_anime":
        cursor.execute("INSERT INTO animes (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (text,))
        conn.commit()
        await update.message.reply_text(f"✅ {text} added successfully.")

    elif action == "admin_add_season":
        parts = text.split("|")
        if len(parts) != 2:
            await update.message.reply_text("Format: Anime Name | Season Number")
            cursor.close()
            release_conn(conn)
            return
        anime_name = parts[0].strip()
        season_number = int(parts[1].strip())
        cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
        result = cursor.fetchone()
        if not result:
            await update.message.reply_text("Anime not found.")
        else:
            anime_id = result[0]
            cursor.execute("""
                INSERT INTO seasons (anime_id, season_number)
                VALUES (%s, %s) ON CONFLICT (anime_id, season_number) DO NOTHING
            """, (anime_id, season_number))
            conn.commit()
            await update.message.reply_text(f"✅ Season {season_number} added to {anime_name}.")

    elif action == "admin_add_episode":
        parts = text.split("|")
        if len(parts) != 3:
            await update.message.reply_text("Format: Anime Name | Season Number | Episode Number")
            cursor.close()
            release_conn(conn)
            return
        anime_name = parts[0].strip()
        season_number = int(parts[1].strip())
        episode_number = int(parts[2].strip())
        await update.message.reply_text(
            f"Now upload video in channel with caption:\n{anime_name} | {season_number} | {episode_number}"
        )

    elif action == "admin_delete_anime":
        cursor.execute("SELECT id FROM animes WHERE name = %s", (text,))
        result = cursor.fetchone()
        if result:
            anime_id = result[0]
            cursor.execute("SELECT id FROM seasons WHERE anime_id = %s", (anime_id,))
            seasons = cursor.fetchall()
            for s in seasons:
                cursor.execute("DELETE FROM episodes WHERE season_id = %s", (s[0],))
            cursor.execute("DELETE FROM seasons WHERE anime_id = %s", (anime_id,))
            cursor.execute("DELETE FROM animes WHERE id = %s", (anime_id,))
            conn.commit()
            await update.message.reply_text("✅ Anime deleted.")
        else:
            await update.message.reply_text("Anime not found.")

    elif action == "admin_delete_season":
        parts = text.split("|")
        if len(parts) != 2:
            await update.message.reply_text("Format: Anime Name | Season Number")
            cursor.close()
            release_conn(conn)
            return
        anime_name = parts[0].strip()
        season_number = int(parts[1].strip())
        cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
        result = cursor.fetchone()
        if result:
            anime_id = result[0]
            cursor.execute("SELECT id FROM seasons WHERE anime_id = %s AND season_number = %s", (anime_id, season_number))
            s = cursor.fetchone()
            if s:
                cursor.execute("DELETE FROM episodes WHERE season_id = %s", (s[0],))
                cursor.execute("DELETE FROM seasons WHERE id = %s", (s[0],))
                conn.commit()
                await update.message.reply_text("✅ Season deleted.")
            else:
                await update.message.reply_text("Season not found.")
        else:
            await update.message.reply_text("Anime not found.")

    elif action == "admin_delete_episode":
        parts = text.split("|")
        if len(parts) != 3:
            await update.message.reply_text("Format: Anime Name | Season Number | Episode Number")
            cursor.close()
            release_conn(conn)
            return
        anime_name = parts[0].strip()
        season_number = int(parts[1].strip())
        episode_number = int(parts[2].strip())
        cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
        result = cursor.fetchone()
        if result:
            anime_id = result[0]
            cursor.execute("SELECT id FROM seasons WHERE anime_id = %s AND season_number = %s", (anime_id, season_number))
            s = cursor.fetchone()
            if s:
                cursor.execute("DELETE FROM episodes WHERE season_id = %s AND episode_number = %s", (s[0], episode_number))
                conn.commit()
                await update.message.reply_text("✅ Episode deleted.")
            else:
                await update.message.reply_text("Season not found.")
        else:
            await update.message.reply_text("Anime not found.")

    cursor.close()
    release_conn(conn)
    admin_state.pop(user_id)


async def handle_text_search(update, context):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if user_id not in user_search_mode:
        return
    user_search_mode.remove(user_id)
    keyword = update.message.text
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM animes WHERE LOWER(name) LIKE LOWER(%s) ORDER BY name ASC
    """, (f"%{keyword}%",))
    results = cursor.fetchall()
    cursor.close()
    release_conn(conn)
    if not results:
        await update.message.reply_text("No anime found.")
        return
    keyboard = []
    for anime in results:
        keyboard.append([InlineKeyboardButton(anime[0], callback_data=f"anime|{anime[0]}")])
    await update.message.reply_text("Search Results:", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_analytics(update, context):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM watch_history")
    total_views = cursor.fetchone()[0]
    cursor.execute("""
        SELECT animes.name, COUNT(*) as views
        FROM watch_history
        JOIN animes ON watch_history.anime_id = animes.id
        GROUP BY animes.id, animes.name
        ORDER BY views DESC LIMIT 1
    """)
    result = cursor.fetchone()
    top_anime = result[0] if result else "N/A"
    top_views = result[1] if result else 0
    cursor.close()
    release_conn(conn)
    await query.edit_message_text(
        f"📊 Analytics\n\n"
        f"👥 Total Users: {total_users}\n"
        f"🎬 Total Episode Views: {total_views}\n"
        f"🔥 Most Watched Anime: {top_anime} ({top_views} views)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]
        ])
    )


async def noop(update, context):
    query = update.callback_query
    await query.answer()


def main():
    init_pool()
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_join, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(show_anime, pattern="^(show_anime|page\\|)"))
    app.add_handler(CallbackQueryHandler(show_seasons, pattern="^(anime\\||seasons\\|)"))
    app.add_handler(CallbackQueryHandler(show_episodes, pattern="^(season_ep\\||eppage\\|)"))
    app.add_handler(CallbackQueryHandler(send_episode, pattern="^episode\\|"))
    app.add_handler(CallbackQueryHandler(noop, pattern="^noop$"))
    app.add_handler(CommandHandler("add_anime", add_anime))
    app.add_handler(CommandHandler("add_season", add_season))
    app.add_handler(CommandHandler("bulk_add", bulk_add))
    app.add_handler(CommandHandler("add_episode", add_episode))
    app.add_handler(CommandHandler("delete_anime", delete_anime))
    app.add_handler(CommandHandler("delete_season", delete_season))
    app.add_handler(CommandHandler("delete_episode", delete_episode))
    app.add_handler(CommandHandler("search", search_anime))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(show_analytics, pattern="^admin_analytics$"))
    app.add_handler(CallbackQueryHandler(handle_admin_actions, pattern="^admin_"))
    app.add_handler(MessageHandler(filters.Chat(CHANNEL_ID) & filters.VIDEO, handle_channel_video))
    app.add_handler(CallbackQueryHandler(enter_search_mode, pattern="^search_mode$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_text), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search), group=2)

    print("🚀 Bot is running with polling...")
    app.run_polling()


if __name__ == "__main__":
    main()









