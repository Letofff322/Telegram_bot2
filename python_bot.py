import os
import tempfile
import uuid
import asyncio
import random
import logging
import subprocess
from pathlib import Path

import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv
import yt_dlp

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.client.default import DefaultBotProperties


# -------------------- НАСТРОЙКИ --------------------

BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "bot_debug.log"
DEBUG_DIR = BASE_DIR / "debug_audios"
DOWNLOAD_DIR = BASE_DIR / "downloads"

DEBUG_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        logging.error("ffmpeg не найден")


check_ffmpeg()
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# -------------------- ХРАНИЛИЩЕ --------------------

VIDEO_REQUESTS: dict[int, str] = {}

# -------------------- УТИЛИТЫ --------------------

def generate_prediction() -> str:
    try:
        with open("predictions.txt", encoding="utf-8") as f:
            return random.choice([x.strip() for x in f if x.strip()])
    except Exception:
        return "Предсказания временно недоступны."


async def transcribe_audio(file_path: str) -> str:
    recognizer = sr.Recognizer()
    tmp = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}.wav"
    try:
        AudioSegment.from_file(file_path).export(tmp, format="wav")
        with sr.AudioFile(str(tmp)) as source:
            return recognizer.recognize_google(recognizer.record(source), language="ru-RU")
    except Exception:
        return "Не удалось распознать речь."
    finally:
        tmp.unlink(missing_ok=True)


# -------------------- VIDEO --------------------

def get_available_qualities(url: str) -> list[int]:
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    return sorted({
        f["height"]
        for f in info.get("formats", [])
        if f.get("vcodec") != "none" and f.get("height") and f["height"] <= 720
    })


def download_video(url: str, height: int) -> Path:
    ydl_opts = {
        "format": f"bestvideo[height={height}]+bestaudio/best",
        "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url)
        return Path(ydl.prepare_filename(info))


# -------------------- ХЕНДЛЕРЫ --------------------

@dp.message(Command("start"))
async def start(message: Message):
    await message.reply("Привет.")


@dp.message(F.voice)
async def voice(message: Message):
    path = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}.ogg"
    await bot.download(message.voice, destination=str(path))
    await message.reply(await transcribe_audio(str(path)))
    path.unlink(missing_ok=True)


@dp.message(
    F.text.contains("tiktok.com")
    | F.text.contains("youtu")
    | F.text.contains("instagram.com")
)
async def video_link(message: Message):
    url = message.text.strip()
    qualities = get_available_qualities(url)

    if not qualities:
        await message.reply("Не удалось получить форматы.")
        return

    VIDEO_REQUESTS[message.message_id] = url

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=f"{q}p",
                callback_data=f"dl:{message.message_id}:{q}"
            ) for q in qualities
        ]]
    )

    await message.reply("Выбери качество:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("dl:"))
async def download_cb(cb: types.CallbackQuery):
    _, msg_id, height = cb.data.split(":")
    url = VIDEO_REQUESTS.get(int(msg_id))

    if not url:
        await cb.answer("Ссылка устарела", show_alert=True)
        return

    await cb.answer("Скачиваю...")

    try:
        path = download_video(url, int(height))
        await cb.message.reply_video(types.FSInputFile(path))
        path.unlink(missing_ok=True)
    except Exception as e:
        logging.exception(e)
        await cb.message.reply("Ошибка при скачивании.")


@dp.inline_query()
async def inline_q(q: InlineQuery):
    if q.query:
        return
    user = q.from_user
    text = generate_prediction()
    await q.answer([
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title="🔮 Предсказание",
            input_message_content=InputTextMessageContent(
                message_text=f"{user.first_name}, {text}"
            )
        )
    ], cache_time=1, is_personal=True)


# -------------------- START --------------------

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
