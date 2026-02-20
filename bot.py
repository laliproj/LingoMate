from supabase import create_client
import os
import random
import logging
import sqlite3
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
from google.genai import Client, types

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

gemini_client = Client(api_key=GEMINI_KEY).aio

WORD_POOL = ["serendipity", "ephemeral", "solitude", "eloquent", "melancholy", "resilient"]
DB_FILE = "word_bank.db"


# ==================== DATABASE HELPERS ====================

def init_db() -> None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS word_bank (
            user_id INTEGER,
            word TEXT,
            PRIMARY KEY (user_id, word)
        )
    ''')
    conn.commit()
    conn.close()


def save_word(user_id: int, word: str) -> None:
    # Supabase "upsert" handles the "ignore if exists" logic automatically
    supabase.table("word_bank").upsert({
