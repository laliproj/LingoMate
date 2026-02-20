from fastapi import FastAPI, Request, Response
from telegram import Update
import sys
import os

# Ensure the root directory is in the path to import bot.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot import get_application

app = FastAPI()

# Lazy singleton — initialized once per cold start
_telegram_app = None

async def get_telegram_app():
    global _telegram_app
    if _telegram_app is None:
        _telegram_app = get_application()
        await _telegram_app.initialize()
    return _telegram_app

@app.post("/api/webhook")
async def webhook_handler(request: Request):
    try:
