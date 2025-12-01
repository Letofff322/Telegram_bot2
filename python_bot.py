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

# Библиотеки для работы с медиа
import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv

# Компоненты aiogram
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram.client.default import DefaultBotProperties

# --- Настройка логирования ---
BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "bot_debug.log"
DEBUG_DIR = BASE_DIR / "debug_audios"
DEBUG_DIR.mkdir(exist_ok=True, mode=0o750)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Проверка ffmpeg (pydub требует ffmpeg)
def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        logging.info("ffmpeg найден.")
    except Exception:
        logging.error("ffmpeg не найден. Установите ffmpeg (например, `sudo apt install ffmpeg`).")
        # не бросаем исключение — бот продолжит работу, но обработка аудио скорее всего упадёт
        # если хотите — можно raise SystemExit("ffmpeg required")

check_ffmpeg()

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Не найден токен Telegram. Укажите его в файле .env под именем TELEGRAM_BOT_TOKEN")

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


def generate_prediction() -> str:
    """Возвращает случайное предсказание из файла predictions.txt."""
    try:
        with open('predictions.txt', 'r', encoding='utf-8') as f:
            predictions = [line.strip() for line in f if line.strip()]
        if not predictions:
            return "Файл с предсказаниями пуст."
        return random.choice(predictions)
    except FileNotFoundError:
        logging.error("Файл 'predictions.txt' не найден. Создайте его рядом с ботом.")
        return "Не могу найти файл с предсказаниями. Обратитесь к администратору."


async def transcribe_audio(file_path: str, chat_id: int | None = None, message_id: int | None = None) -> str:
    """
    Конвертирует аудио в WAV (через pydub/ffmpeg) и распознает речь.
    При ошибке сохраняет проблемные файлы в debug_audios и пишет подробный лог.
    Возвращает распознанный текст или строку с сообщением об ошибке.
    """
    recognizer = sr.Recognizer()
    tmp_wav = None
    # уникальный префикс для debug-имен
    uid = uuid.uuid4().hex
    try:
        # Загружаем исходный файл через pydub (поддерживает ogg/mp4 и т.д.)
        audio = AudioSegment.from_file(file_path)
        # создаём временный wav-файл в /tmp с уникальным именем
        tmp_wav = Path(tempfile.gettempdir()) / f"voice_{chat_id or 'anon'}_{message_id or uid}_{uid}.wav"
        audio.export(tmp_wav, format='wav')

        # Используем speech_recognition для загрузки и распознавания
        with sr.AudioFile(str(tmp_wav)) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='ru-RU')
            return text

    except sr.UnknownValueError:
        return "Не удалось распознать речь."
    except sr.RequestError as e:
        logging.exception("RequestError при обращении к API распознавания: %s", e)
        return "Ошибка API распознавания речи."
    except Exception as e:
        # Подробный лог и сохранение проблемных файлов для последующего анализа
        logging.exception("Ошибка обработки аудио (chat=%s, msg=%s): %s", chat_id, message_id, e)
        tb = traceback.format_exc()
        logging.error("Traceback:\n%s", tb)

        # Сохраняем исходный файл и wav в debug_audios
        try:
            debug_prefix = f"problem_{chat_id or 'anon'}_{message_id or uid}_{uid}"
            # копируем оригинал
            if os.path.exists(file_path):
                dest_ogg = DEBUG_DIR / (debug_prefix + Path(file_path).suffix)
                shutil.copy2(file_path, dest_ogg)
                logging.info("Сохранён проблемный исходный файл: %s", dest_ogg)
            # копируем wav если он есть
            if tmp_wav and Path(tmp_wav).exists():
                dest_wav = DEBUG_DIR / (debug_prefix + ".wav")
                shutil.copy2(str(tmp_wav), dest_wav)
                logging.info("Сохранён проблемный wav: %s", dest_wav)
        except Exception:
            logging.exception("Не удалось сохранить проблемные файлы для отладки.")

        return "Произошла ошибка при обработке аудио."
    finally:
        # Удаляем временные файлы, которые создали внутри этой функции (но не оригинал до тех пор, пока не скопирован)
        try:
            if tmp_wav and Path(tmp_wav).exists():
                Path(tmp_wav).unlink(missing_ok=True)
        except Exception:
            logging.exception("Не удалось удалить временный wav: %s", tmp_wav)


@dp.message(Command("start"))
async def handle_start(message: Message):
    """Отвечает на команду /start."""
    await message.reply("Привет! Сосал?")


@dp.message(F.voice)
async def handle_voice(message: Message):
    """Обрабатывает голосовые сообщения."""
    # создаём уникальный временный файл для загрузки (в /tmp)
    uid = uuid.uuid4().hex
    download_path = Path(tempfile.gettempdir()) / f"voice_in_{message.chat.id}_{message.message_id}_{uid}.ogg"
    try:
        await bot.download(message.voice, destination=str(download_path))
        logging.info("Скачан voice в %s", download_path)
        text = await transcribe_audio(str(download_path), chat_id=message.chat.id, message_id=message.message_id)
        await message.reply(f"<b>Расшифровка:</b>\n\n<i>{text}</i>")
    except Exception as e:
        logging.exception("Ошибка в handle_voice: %s", e)
        await message.reply("Произошла ошибка при обработке голосового сообщения.")
    finally:
        # пытаемся удалить загруженный файл (если не скопирован в debug_audios)
        try:
            if download_path.exists():
                download_path.unlink(missing_ok=True)
        except Exception:
            logging.exception("Не удалось удалить загруженный файл %s", download_path)


@dp.message(F.video_note)
async def handle_video_note(message: Message):
    """Обрабатывает видео-кружочки."""
    uid = uuid.uuid4().hex
    download_path = Path(tempfile.gettempdir()) / f"videonote_in_{message.chat.id}_{message.message_id}_{uid}.mp4"
    try:
        await bot.download(message.video_note, destination=str(download_path))
        logging.info("Скачан video_note в %s", download_path)
        text = await transcribe_audio(str(download_path), chat_id=message.chat.id, message_id=message.message_id)
        await message.reply(f"<b>Расшифровка кружочка:</b>\n\n<i>{text}</i>")
    except Exception as e:
        logging.exception("Ошибка в handle_video_note: %s", e)
        await message.reply("Произошла ошибка при обработке видео-кружочка.")
    finally:
        try:
            if download_path.exists():
                download_path.unlink(missing_ok=True)
        except Exception:
            logging.exception("Не удалось удалить загруженный файл %s", download_path)


@dp.inline_query()
async def handle_inline_query(inline_query: InlineQuery):
    """Обрабатывает инлайн-запросы для предсказаний."""
    query_text = inline_query.query
    user = inline_query.from_user
    results = []

    if not query_text:
        user_tag = f"@{user.username}" if user.username else user.first_name
        prediction = generate_prediction()
        response_text = f"Предсказание для {user_tag}:\n\n{prediction}"
        input_content = InputTextMessageContent(message_text=response_text)
        result = InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title="🔮 Получить предсказание",
            description="Нажмите, чтобы отправить предсказание в чат.",
            input_message_content=input_content,
            thumbnail_url="https://i.imgur.com/s8OQ0dF.png",
        )
        results.append(result)

    await inline_query.answer(results=results, cache_time=1, is_personal=True)


async def on_startup():
    """Выполняется при запуске бота."""
    logging.info("Бот запущен и готов к работе!")


async def main():
    """Основная функция для запуска бота."""
    dp.startup.register(on_startup)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
