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


# ==========================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hello! I am your AI-powered English Tutor bot. 🤖\n\n"
        "Commands:\n"
        "/word - Get a random word\n"
        "/flashcard - Test your vocabulary\n"
        "/mywords - View your saved Word Bank\n"
        "/refine [sentence] - Analyze grammar and correct mistakes"
    )


async def word_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_chat_action("typing")
    random_word = random.choice(WORD_POOL)
    word_data = await fetch_word_details(random_word)

    if word_data:
        save_word(update.effective_user.id, random_word)
        message = f"📖 *Word:* {word_data['word']}\n\n💡 *Definition:* {word_data['definition']}\n\n📝 *Example:* _{word_data['example']}_"
        await update.message.reply_text(message, parse_mode="Markdown")
    else:
        await update.message.reply_text("Oops! Had trouble reaching the dictionary.")


async def flashcard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_chat_action("typing")
    random_word = random.choice(WORD_POOL)
    word_data = await fetch_word_details(random_word)

    if word_data:
        save_word(update.effective_user.id, random_word)
        if "flashcards" not in context.user_data:
            context.user_data["flashcards"] = {}
        context.user_data["flashcards"][random_word] = word_data

        keyboard = [[InlineKeyboardButton("👀 Show Meaning", callback_data=f"reveal:{random_word}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🧠 *Flashcard Memory Test*\n\nDo you know what this word means?\n\n*Word:* {word_data['word']}",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )


async def flashcard_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    if callback_data.startswith("reveal:"):
        word_key = callback_data.split(":")[1]
        word_data = context.user_data.get("flashcards", {}).get(word_key)
        if word_data:
            revealed_text = f"🧠 *Flashcard Revealed*\n\n📖 *Word:* {word_data['word']}\n\n💡 *Definition:* {word_data['definition']}\n\n📝 *Example:* _{word_data['example']}_"
            await query.edit_message_text(text=revealed_text, parse_mode="Markdown")


async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sentence_to_explain = " ".join(context.args)
    if not sentence_to_explain.strip():
        await update.message.reply_text(
            "⚠️ Please provide a sentence to analyze.\n\nExample: /explain Me going to the store yesterday"
        )
        return

    await update.message.reply_chat_action("typing")
    try:
        config = types.GenerateContentConfig(
            system_instruction=(
                "You are a quick, casual English conversation coach. "
                "CRITICAL RULES:\n"
                "1. NEVER use markdown formatting. NO stars, NO asterisks, NO bold text. Use plain text only.\n"
                "2. NEVER break down the grammar word-by-word. Do not use academic terms.\n"
                "3. KEEP IT SHORT. Max 3 sentences total.\n"
                "If the sentence is okay, say 'Looks good!' and give one natural alternative. "
                "If it has a mistake, just provide the correct version and explain why in one simple, plain sentence."
            )
        )

        response = await gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=sentence_to_explain,
            config=config
        )

        # Safe, plain text header
        await update.message.reply_text(f"🤖 Tutor Analysis for: \"{sentence_to_explain}\"")

        # The AI's response, which should now be free of asterisks
        await update.message.reply_text(response.text)

    except Exception as e:
        await update.message.reply_text(f"❌ Raw Error Details:\n\n{str(e)}")


async def mywords_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_first_name = update.effective_user.first_name
    saved_words = get_user_words(user_id)

    if not saved_words:
        await update.message.reply_text(
            "📚 Your Word Bank is currently empty!\n\nUse /word or /flashcard to start collecting words.")
        return

    formatted_list = "\n".join([f"• {word.capitalize()}" for word in saved_words])
    await update.message.reply_text(
        f"📚 *{user_first_name}'s Word Bank* ({len(saved_words)} words):\n\n{formatted_list}", parse_mode="Markdown")


def get_application() -> Application:
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        raise ValueError("TELEGRAM_BOT_TOKEN not found")
    if not GEMINI_KEY:
        logger.error("GEMINI_API_KEY not found!")
        raise ValueError("GEMINI_API_KEY not found")

    init_db()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("word", word_command))
    application.add_handler(CommandHandler("flashcard", flashcard_command))
    application.add_handler(CallbackQueryHandler(flashcard_button_handler))
    application.add_handler(CommandHandler("refine", explain_command))
    application.add_handler(CommandHandler("mywords", mywords_command))
    
    return application

def main() -> None:
    try:
        application = get_application()
        logger.info("Bot is starting up in polling mode... Press Ctrl+C to stop it.")
        application.run_polling()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()