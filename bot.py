CHANNEL_ID = -1003819722036
ADMIN_ID = 6374990539

from telegram.ext import MessageHandler, filters


import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ================================
# 🔥 PASTE YOUR BOT TOKEN HERE
# ================================

import os
BOT_TOKEN = os.getenv("BOT_TOKEN")

ANIME_PER_PAGE = 10

user_cooldown = {}

def is_spamming(user_id):
    now = asyncio.get_event_loop().time()

    if user_id in user_cooldown:
        if now - user_cooldown[user_id] < 2:  # 2 sec cooldown
            return True

    user_cooldown[user_id] = now
    return False

# =====================================================
# ===== EDIT YOUR ANIME LIST + EPISODES HERE =========
# =====================================================

#anime_data = {
    #"Attack on Titan": {
    #    "Episode 1": "M1.mp4",
   #     "Episode 2": "videos/aot_ep2.mp4",
   # },
   # "Naruto": {
    #    "Episode 1": "videos/naruto_ep1.mp4",
  #  },
#}

# =====================================================
# ========== DO NOT EDIT BELOW THIS LINE =============
# =====================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

     user_id = update.effective_user.id

     conn = sqlite3.connect("anime.db")
     cursor = conn.cursor()

     cursor.execute("""
     INSERT INTO users (user_id, last_active, total_requests)
     VALUES (?, CURRENT_TIMESTAMP, 1)
     ON CONFLICT(user_id)
     DO UPDATE SET
     last_active=CURRENT_TIMESTAMP,
     total_requests=total_requests+1
     """, (user_id,))

     conn.commit()
     conn.close()

     keyboard = [
        [InlineKeyboardButton("📚 Browse Anime", callback_data="show_anime")]
    ]

    # Show Admin Panel button only to you
     if update.effective_user.id == ADMIN_ID:
        keyboard.append(
            [InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")]
        )

     reply_markup = InlineKeyboardMarkup(keyboard)

     await update.message.reply_text(
        "Welcome! Choose an option:",
        reply_markup=reply_markup,
    )
 

async def show_anime(update, context):
    query = update.callback_query
    await query.answer()

    page = 0
    if query.data.startswith("page|"):
        page = int(query.data.split("|")[1])

    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM animes")
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT name FROM animes
        ORDER BY name ASC
        LIMIT ? OFFSET ?
      """, (ANIME_PER_PAGE, page * ANIME_PER_PAGE))

    animes = cursor.fetchall()
    conn.close()

    keyboard = []

# 🔍 Search button at top
    keyboard.append([
    InlineKeyboardButton("🔍 Search", callback_data="search_mode")
])

# Anime buttons
    for anime in animes:
     keyboard.append([
        InlineKeyboardButton(anime[0], callback_data=f"anime|{anime[0]}")
    ])
    nav_buttons = []

    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅ Previous", callback_data=f"page|{page-1}")
        )

    if (page + 1) * ANIME_PER_PAGE < total:
        nav_buttons.append(
            InlineKeyboardButton("Next ➡", callback_data=f"page|{page+1}")
        )

    if nav_buttons:
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "Select an anime:",
        reply_markup=reply_markup
    )
    
async def show_episodes(update, context):   
     query = update.callback_query
     await query.answer()

     _, anime_name = query.data.split("|")

     conn = sqlite3.connect("anime.db")
     cursor = conn.cursor()

     cursor.execute("SELECT id FROM animes WHERE name = ?", (anime_name,))
     anime_id = cursor.fetchone()[0]

     cursor.execute("""
        SELECT episode_number 
        FROM episodes 
        WHERE anime_id = ?
        ORDER BY episode_number ASC
    """, (anime_id,))

     episodes = cursor.fetchall()
     conn.close()

     keyboard = []
     for ep in episodes:
        keyboard.append([
            InlineKeyboardButton(
                f"Episode {ep[0]}",
                callback_data=f"episode|{anime_id}|{ep[0]}"
            )
        ])
      
     keyboard.append([
    InlineKeyboardButton("🔙 Back", callback_data="show_anime")
   ])
     
     reply_markup = InlineKeyboardMarkup(keyboard)

     msg = await query.edit_message_text(
        f"{anime_name} Episodes:",
        reply_markup=reply_markup
    )

async def send_episode(update, context):
    query = update.callback_query
    await query.answer()

    # Anti-spam check
    if is_spamming(query.from_user.id):
        await query.answer("Please slow down 😄", show_alert=True)
        return

    _, anime_id, episode_number = query.data.split("|")

    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT file_id 
        FROM episodes 
        WHERE anime_id = ? AND episode_number = ?
    """, (anime_id, episode_number))

    result = cursor.fetchone()
    conn.close()

    if not result:
        await query.answer("Episode not found!", show_alert=True)
        return

    file_id = result[0]

    # Send video
    video_msg = await query.message.reply_video(
        video=file_id,
        caption=f"Episode {episode_number}"
    )

    # Track view
    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO watch_history (user_id, anime_id, episode_number)
        VALUES (?, ?, ?)
    """, (query.from_user.id, anime_id, episode_number))

    conn.commit()
    conn.close()

    warning_msg = await query.message.reply_text(
        "All messages will be deleted in 5 minutes."
    )

    asyncio.create_task(
        auto_delete([
            video_msg,
            warning_msg,
            query.message
        ])
    )

async def add_anime(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: /add_anime Anime Name")
        return

    anime_name = " ".join(context.args)

    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    cursor.execute("INSERT OR IGNORE INTO animes (name) VALUES (?)", (anime_name,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"{anime_name} added successfully.")

async def add_episode(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /add_episode Anime_Name EpisodeNumber")
        return

    episode_number = int(context.args[-1])
    anime_name = " ".join(context.args[:-1])

    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM animes WHERE name = ?", (anime_name,))
    result = cursor.fetchone()

    if not result:
        await update.message.reply_text("Anime not found.")
        conn.close()
        return

    conn.close()

    await update.message.reply_text(
        f"Now upload the episode video to the storage channel with caption:\n\n{anime_name} | {episode_number}"
    )

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
        if len(parts) != 2:
          print("Caption format incorrect")
          return

        anime_name = parts[0].strip()
        episode_number = int(parts[1].strip())

        conn = sqlite3.connect("anime.db")
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM animes WHERE name = ?", (anime_name,))
        result = cursor.fetchone()

        if not result:
            conn.close()
            return

        anime_id = result[0]

        cursor.execute("""
    INSERT INTO episodes (anime_id, episode_number, file_id)
    VALUES (?, ?, ?)
    ON CONFLICT(anime_id, episode_number)
    DO UPDATE SET file_id=excluded.file_id
""", (anime_id, episode_number, file_id))

        conn.commit()
        conn.close()

async def auto_delete(messages):
    await asyncio.sleep(300)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass


async def search_anime(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /search keyword")
        return

    keyword = " ".join(context.args)

    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name FROM animes
        WHERE LOWER(name) LIKE LOWER(?)
        ORDER BY name ASC
    """, (f"%{keyword}%",))

    results = cursor.fetchall()
    conn.close()

    if not results:
        await update.message.reply_text("No anime found.")
        return
   
    keyboard = []
# Anime buttons 
    for anime in results:
        keyboard.append([
            InlineKeyboardButton(anime[0], callback_data=f"anime|{anime[0]}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Search Results:",
        reply_markup=reply_markup
    )
async def delete_episode(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /delete_episode Anime_Name EpisodeNumber"
        )
        return

    episode_number = int(context.args[-1])
    anime_name = " ".join(context.args[:-1])

    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM animes WHERE name = ?", (anime_name,))
    result = cursor.fetchone()

    if not result:
        await update.message.reply_text("Anime not found.")
        conn.close()
        return

    anime_id = result[0]

    cursor.execute("""
        DELETE FROM episodes
        WHERE anime_id = ? AND episode_number = ?
    """, (anime_id, episode_number))

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"Episode {episode_number} deleted successfully."
    )

async def delete_anime(update, context):
     if update.effective_user.id != ADMIN_ID:
        return

     if not context.args:
        await update.message.reply_text(
            "Usage: /delete_anime Anime_Name"
        )
        return

     anime_name = " ".join(context.args)

     conn = sqlite3.connect("anime.db")
     cursor = conn.cursor()

     cursor.execute("SELECT id FROM animes WHERE name = ?", (anime_name,))
     result = cursor.fetchone()

     if not result:
        await update.message.reply_text("Anime not found.")
        conn.close()
        return

     anime_id = result[0]

     cursor.execute("DELETE FROM episodes WHERE anime_id = ?", (anime_id,))
     cursor.execute("DELETE FROM animes WHERE id = ?", (anime_id,))

     conn.commit()
     conn.close()

     await update.message.reply_text(
        f"{anime_name} and all its episodes deleted successfully."
    )

user_search_mode = set()

async def enter_search_mode(update, context):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_search_mode.add(user_id)

    await query.message.reply_text(
        "Type the anime name you want to search:"
    )

async def handle_admin_text(update, context):
    user_id = update.effective_user.id

    if user_id not in admin_state:
        return

    action = admin_state[user_id]
    text = update.message.text.strip()

    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    if action == "admin_add_anime":
        cursor.execute("INSERT OR IGNORE INTO animes (name) VALUES (?)", (text,))
        conn.commit()
        await update.message.reply_text(f"{text} added successfully.")

    elif action == "admin_delete_anime":
        cursor.execute("SELECT id FROM animes WHERE name = ?", (text,))
        result = cursor.fetchone()

        if result:
            anime_id = result[0]
            cursor.execute("DELETE FROM episodes WHERE anime_id = ?", (anime_id,))
            cursor.execute("DELETE FROM animes WHERE id = ?", (anime_id,))
            conn.commit()
            await update.message.reply_text("Anime deleted.")
        else:
            await update.message.reply_text("Anime not found.")

    elif action in ["admin_add_episode", "admin_delete_episode"]:
        parts = text.split("|")
        if len(parts) != 2:
            await update.message.reply_text("Format must be: Anime Name | EpisodeNumber")
            conn.close()
            return

        anime_name = parts[0].strip()
        episode_number = int(parts[1].strip())

        cursor.execute("SELECT id FROM animes WHERE name = ?", (anime_name,))
        result = cursor.fetchone()

        if not result:
            await update.message.reply_text("Anime not found.")
            conn.close()
            return

        anime_id = result[0]

        if action == "admin_delete_episode":
            cursor.execute("""
                DELETE FROM episodes
                WHERE anime_id = ? AND episode_number = ?
            """, (anime_id, episode_number))
            conn.commit()
            await update.message.reply_text("Episode deleted.")

        elif action == "admin_add_episode":
            await update.message.reply_text(
                f"Now upload video in channel with caption:\n{anime_name} | {episode_number}"
            )

    conn.close()
    admin_state.pop(user_id)

async def handle_text_search(update, context):
    user_id = update.effective_user.id

    if user_id not in user_search_mode:
        return

    user_search_mode.remove(user_id)

    keyword = update.message.text

    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name FROM animes
        WHERE LOWER(name) LIKE LOWER(?)
        ORDER BY name ASC
    """, (f"%{keyword}%",))

    results = cursor.fetchall()
    conn.close()

    if not results:
        await update.message.reply_text("No anime found.")
        return

    keyboard = []
    for anime in results:
        keyboard.append([
            InlineKeyboardButton(anime[0], callback_data=f"anime|{anime[0]}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Search Results:",
        reply_markup=reply_markup
    )  

async def admin_panel(update, context):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    keyboard = [
    [InlineKeyboardButton("➕ Add Anime", callback_data="admin_add_anime")],
    [InlineKeyboardButton("➕ Add Episode", callback_data="admin_add_episode")],
    [InlineKeyboardButton("❌ Delete Anime", callback_data="admin_delete_anime")],
    [InlineKeyboardButton("❌ Delete Episode", callback_data="admin_delete_episode")],
    [InlineKeyboardButton("📊 Analytics", callback_data="admin_analytics")],
    [InlineKeyboardButton("🔙 Back", callback_data="show_anime")]
]

    await query.edit_message_text(
        "🛠 Admin Panel",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

admin_state = {}

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

    elif action == "admin_add_episode":
        await query.message.reply_text(
            "Send: Anime Name | Episode Number\n\nExample:\nNaruto | 1"
        )

    elif action == "admin_delete_anime":
        await query.message.reply_text("Send anime name to delete:")

    elif action == "admin_delete_episode":
        await query.message.reply_text(
            "Send: Anime Name | Episode Number to delete"
        )

async def show_analytics(update, context):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    # Total users
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    # Total views
    cursor.execute("SELECT COUNT(*) FROM watch_history")
    total_views = cursor.fetchone()[0]

    # Most watched anime
    cursor.execute("""
        SELECT animes.name, COUNT(*) as views
        FROM watch_history
        JOIN animes ON watch_history.anime_id = animes.id
        GROUP BY anime_id
        ORDER BY views DESC
        LIMIT 1
    """)
    result = cursor.fetchone()

    if result:
        top_anime = result[0]
        top_views = result[1]
    else:
        top_anime = "N/A"
        top_views = 0

    conn.close()

    stats_text = f"""
📊 Analytics

👥 Total Users: {total_users}
🎬 Total Episode Views: {total_views}
🔥 Most Watched Anime: {top_anime} ({top_views} views)
"""

    await query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]
        ])
    )

import sqlite3

def init_db():
    conn = sqlite3.connect("anime.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_active TIMESTAMP,
        total_requests INTEGER DEFAULT 0
    )
    """)

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
        UNIQUE(anime_id, episode_number)
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

    conn.commit()
    conn.close()

def main():
    init_db() 
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(show_anime, pattern="^(show_anime|page\\|)"))
    app.add_handler(CallbackQueryHandler(show_episodes, pattern="^anime\\|"))
    app.add_handler(CallbackQueryHandler(send_episode, pattern="^episode\\|"))
    app.add_handler(CommandHandler("add_anime", add_anime))
    app.add_handler(CommandHandler("add_episode", add_episode))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="admin_panel"))
    app.add_handler(CallbackQueryHandler(show_analytics, pattern="admin_analytics"))
    app.add_handler(CallbackQueryHandler(handle_admin_actions, pattern="^admin_"))
    app.add_handler(MessageHandler(filters.Chat(CHANNEL_ID) & filters.VIDEO, handle_channel_video))
    app.add_handler(CommandHandler("search", search_anime))
    app.add_handler(CommandHandler("delete_episode", delete_episode))
    app.add_handler(CommandHandler("delete_anime", delete_anime))
    app.add_handler(CallbackQueryHandler(enter_search_mode, pattern="search_mode"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_text), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search), group=2)
    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":

    main()

