import os
import tempfile
import uuid
import asyncio
import random
import logging
import traceback
import shutil
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

DEBUG_DIR.mkdir(exist_ok=True, mode=0o750)
DOWNLOAD_DIR.mkdir(exist_ok=True, mode=0o750)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)


def check_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        logging.info("ffmpeg найден.")
    except Exception:
        logging.error("ffmpeg не найден. Установите ffmpeg.")


check_ffmpeg()

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN")

bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

# -------------------- УТИЛИТЫ --------------------

def generate_prediction() -> str:
    try:
        with open("predictions.txt", "r", encoding="utf-8") as f:
            predictions = [line.strip() for line in f if line.strip()]
        return random.choice(predictions) if predictions else "Файл пуст."
    except FileNotFoundError:
        return "Файл с предсказаниями не найден."


async def transcribe_audio(file_path: str, chat_id=None, message_id=None) -> str:
    recognizer = sr.Recognizer()
    tmp_wav = None
    uid = uuid.uuid4().hex

    try:
        audio = AudioSegment.from_file(file_path)
        tmp_wav = Path(tempfile.gettempdir()) / f"audio_{uid}.wav"
        audio.export(tmp_wav, format="wav")

        with sr.AudioFile(str(tmp_wav)) as source:
            audio_data = recognizer.record(source)
            return recognizer.recognize_google(audio_data, language="ru-RU")

    except sr.UnknownValueError:
        return "Не удалось распознать речь."
    except Exception as e:
        logging.exception("Ошибка распознавания: %s", e)
        return "Ошибка обработки аудио."
    finally:
        if tmp_wav and tmp_wav.exists():
            tmp_wav.unlink(missing_ok=True)


# -------------------- СКАЧИВАНИЕ ВИДЕО --------------------

def is_video_link(text: str) -> bool:
    return any(x in text for x in (
        "tiktok.com",
        "youtube.com",
        "youtu.be",
        "instagram.com",
    ))


def get_available_qualities(url: str) -> list[int]:
    ydl_opts = {"quiet": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    heights = set()
    for f in info.get("formats", []):
        if f.get("vcodec") != "none" and f.get("height"):
            heights.add(f["height"])

    return sorted(h for h in heights if h <= 720)


def download_video(url: str, height: int) -> Path:
    outtmpl = DOWNLOAD_DIR / "%(id)s.%(ext)s"
    ydl_opts = {
        "format": f"bestvideo[height={height}]+bestaudio/best/best",
        "outtmpl": str(outtmpl),
        "merge_output_format": "mp4",
        "quiet": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url)
        return Path(ydl.prepare_filename(info))


# -------------------- ХЕНДЛЕРЫ --------------------

@dp.message(Command("start"))
async def handle_start(message: Message):
    await message.reply("Привет! Сосал?")


@dp.message(F.voice)
async def handle_voice(message: Message):
    uid = uuid.uuid4().hex
    path = Path(tempfile.gettempdir()) / f"voice_{uid}.ogg"

    try:
        await bot.download(message.voice, destination=str(path))
        text = await transcribe_audio(str(path), message.chat.id, message.message_id)
        await message.reply(f"<b>Расшифровка:</b>\n\n<i>{text}</i>")
    finally:
        path.unlink(missing_ok=True)


@dp.message(F.video_note)
async def handle_video_note(message: Message):
    uid = uuid.uuid4().hex
    path = Path(tempfile.gettempdir()) / f"videonote_{uid}.mp4"

    try:
        await bot.download(message.video_note, destination=str(path))
        text = await transcribe_audio(str(path), message.chat.id, message.message_id)
        await message.reply(f"<b>Расшифровка кружочка:</b>\n\n<i>{text}</i>")
    finally:
        path.unlink(missing_ok=True)


@dp.message(F.text)
async def handle_video_links(message: Message):
    if not is_video_link(message.text):
        return

    url = message.text.strip()
    qualities = get_available_qualities(url)

    if not qualities:
        await message.reply("Не удалось определить доступные качества.")
        return

    buttons = [
        InlineKeyboardButton(
            text=f"{q}p",
            callback_data=f"dl|{q}|{url}"
        ) for q in qualities
    ]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[buttons]
    )

    await message.reply(
        "Выбери качество для скачивания:",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("dl|"))
async def handle_download(callback: types.CallbackQuery):
    _, height, url = callback.data.split("|", 2)
    height = int(height)

    await callback.answer("Скачиваю...")

    try:
        video_path = download_video(url, height)

        await callback.message.reply_video(
            video=types.FSInputFile(video_path),
            reply_to_message_id=callback.message.reply_to_message.message_id
        )

        video_path.unlink(missing_ok=True)

    except Exception as e:
        logging.exception("Ошибка скачивания: %s", e)
        await callback.message.reply("Ошибка при скачивании видео.")


@dp.inline_query()
async def handle_inline_query(inline_query: InlineQuery):
    if inline_query.query:
        return

    user = inline_query.from_user
    user_tag = f"@{user.username}" if user.username else user.first_name
    prediction = generate_prediction()

    result = InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title="🔮 Получить предсказание",
        input_message_content=InputTextMessageContent(
            message_text=f"Предсказание для {user_tag}:\n\n{prediction}"
        ),
    )

    await inline_query.answer([result], cache_time=1, is_personal=True)


# -------------------- ЗАПУСК --------------------

async def on_startup():
    logging.info("Бот запущен.")


async def main():
    dp.startup.register(on_startup)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
