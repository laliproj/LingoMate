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
        "user_id": user_id,
        "word": word.lower()
    }).execute()

def get_user_words(user_id: int) -> list:
    response = supabase.table("word_bank").select("word").eq("user_id", user_id).order("word").execute()
    # Extract just the word strings from the response data
    return [item["word"] for item in response.data]

# ==================== API FETCH FUNCTION ====================

async def fetch_word_details(word: str) -> dict:
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                meanings = data[0].get("meanings", [])
                if meanings:
                    definitions = meanings[0].get("definitions", [])
                    if definitions:
                        primary_def = definitions[0].get("definition", "No definition found.")
                        example = definitions[0].get("example")

                        if not example:
                            try:
                                prompt = (
                                    f"Write a single, natural example sentence using the word '{word}' "
                                    f"based on this definition: '{primary_def}'. "
                                    f"Provide ONLY the sentence text, without any quotes, introductions, or extra explanations."
                                )
                                gemini_response = await gemini_client.models.generate_content(
                                    model="gemini-2.5-flash",
                                    contents=prompt
                                )
                                example = gemini_response.text.strip()
                            except Exception as gemini_err:
                                example = f"⚠️ Gemini Error: {gemini_err}"

                        return {
                            "word": word.capitalize(),
                            "definition": primary_def,
                            "example": example
                        }
        except Exception as e:
            logger.error(f"Error fetching data from Dictionary API: {e}")
    return None
