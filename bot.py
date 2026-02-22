CHANNEL_ID = -1003819722036
ADMIN_ID = 6374990539

import os
import asyncio
import psycopg2
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ANIME_PER_PAGE = 10
user_cooldown = {}
admin_state = {}
user_search_mode = set()

# ================= DATABASE =================

def get_connection():
    url = urlparse(DATABASE_URL)
    return psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_active TIMESTAMP,
        total_requests INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS animes (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS episodes (
        id SERIAL PRIMARY KEY,
        anime_id INTEGER REFERENCES animes(id) ON DELETE CASCADE,
        episode_number INTEGER,
        file_id TEXT,
        UNIQUE(anime_id, episode_number)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS watch_history (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        anime_id INTEGER,
        episode_number INTEGER,
        watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    cursor.close()
    conn.close()

# ================= UTILITIES =================

def is_spamming(user_id):
    now = asyncio.get_event_loop().time()
    if user_id in user_cooldown:
        if now - user_cooldown[user_id] < 2:
            return True
    user_cooldown[user_id] = now
    return False

async def auto_delete(messages):
    await asyncio.sleep(300)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = get_connection()
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
    conn.close()

    keyboard = [[InlineKeyboardButton("📚 Browse Anime", callback_data="show_anime")]]

    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])

    await update.message.reply_text(
        "Welcome! Choose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= SHOW ANIME =================

async def show_anime(update, context):
    query = update.callback_query
    await query.answer()

    page = 0
    if query.data.startswith("page|"):
        page = int(query.data.split("|")[1])

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM animes")
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT name FROM animes
        ORDER BY name ASC
        LIMIT %s OFFSET %s
    """, (ANIME_PER_PAGE, page * ANIME_PER_PAGE))

    animes = cursor.fetchall()
    cursor.close()
    conn.close()

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

    await query.edit_message_text(
        "Select an anime:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= SHOW EPISODES =================

async def show_episodes(update, context):
    query = update.callback_query
    await query.answer()

    _, anime_name = query.data.split("|")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM animes WHERE name = %s", (anime_name,))
    result = cursor.fetchone()

    if not result:
        cursor.close()
        conn.close()
        return

    anime_id = result[0]

    cursor.execute("""
        SELECT episode_number
        FROM episodes
        WHERE anime_id = %s
        ORDER BY episode_number ASC
    """, (anime_id,))

    episodes = cursor.fetchall()
    cursor.close()
    conn.close()

    keyboard = []
    for ep in episodes:
        keyboard.append([
            InlineKeyboardButton(
                f"Episode {ep[0]}",
                callback_data=f"episode|{anime_id}|{ep[0]}"
            )
        ])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="show_anime")])

    await query.edit_message_text(
        f"{anime_name} Episodes:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= SEND EPISODE =================

async def send_episode(update, context):
    query = update.callback_query
    await query.answer()

    if is_spamming(query.from_user.id):
        await query.answer("Please slow down 😄", show_alert=True)
        return

    _, anime_id, episode_number = query.data.split("|")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT file_id
        FROM episodes
        WHERE anime_id = %s AND episode_number = %s
    """, (anime_id, episode_number))

    result = cursor.fetchone()

    if not result:
        cursor.close()
        conn.close()
        await query.answer("Episode not found!", show_alert=True)
        return

    file_id = result[0]

    cursor.execute("""
        INSERT INTO watch_history (user_id, anime_id, episode_number)
        VALUES (%s, %s, %s)
    """, (query.from_user.id, anime_id, episode_number))

    conn.commit()
    cursor.close()
    conn.close()

    video_msg = await query.message.reply_video(
        video=file_id,
        caption=f"Episode {episode_number}"
    )

    warning_msg = await query.message.reply_text(
        "All messages will be deleted in 5 minutes."
    )

    asyncio.create_task(auto_delete([video_msg, warning_msg, query.message]))

# ================= ADD / DELETE / ANALYTICS =================

async def add_anime(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    anime_name = " ".join(context.args)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO animes (name) VALUES (%s) ON CONFLICT DO NOTHING", (anime_name,))
    conn.commit()
    cursor.close()
    conn.close()

    await update.message.reply_text("Anime added successfully.")

async def delete_anime(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    anime_name = " ".join(context.args)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM animes WHERE name = %s", (anime_name,))
    conn.commit()
    cursor.close()
    conn.close()

    await update.message.reply_text("Anime deleted.")

async def show_analytics(update, context):
    query = update.callback_query
    await query.answer()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM watch_history")
    total_views = cursor.fetchone()[0]

    cursor.execute("""
        SELECT animes.name, COUNT(*) as views
        FROM watch_history
        JOIN animes ON watch_history.anime_id = animes.id
        GROUP BY animes.name
        ORDER BY views DESC
        LIMIT 1
    """)
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    top_anime = result[0] if result else "N/A"
    top_views = result[1] if result else 0

    await query.edit_message_text(
        f"📊 Analytics\n\n👥 Users: {total_users}\n🎬 Views: {total_views}\n🔥 Top: {top_anime} ({top_views})",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]])
    )

# ================= MAIN =================

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_anime", add_anime))
    app.add_handler(CommandHandler("delete_anime", delete_anime))
    app.add_handler(CallbackQueryHandler(show_anime, pattern="^(show_anime|page\\|)"))
    app.add_handler(CallbackQueryHandler(show_episodes, pattern="^anime\\|"))
    app.add_handler(CallbackQueryHandler(send_episode, pattern="^episode\\|"))
    app.add_handler(CallbackQueryHandler(show_analytics, pattern="admin_analytics"))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
