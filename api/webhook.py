from fastapi import FastAPI, Request, Response
from telegram import Update
import sys
import os

# Ensure the root directory is in the path to import bot.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot import get_application
