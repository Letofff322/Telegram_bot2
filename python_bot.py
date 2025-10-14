import os
import tempfile
import uuid
import asyncio
import random
import logging

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


logging.basicConfig(level=logging.INFO)
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



async def transcribe_audio(file_path: str) -> str:
    """Конвертирует аудио в WAV и распознает речь."""
    recognizer = sr.Recognizer()
    temp_wav = None
    try:
        audio = AudioSegment.from_file(file_path)
        temp_wav = tempfile.mktemp(suffix=".wav")
        audio.export(temp_wav, format='wav')
        
        with sr.AudioFile(temp_wav) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='ru-RU')
            return text
    except sr.UnknownValueError:
        return "Не удалось распознать речь."
    except sr.RequestError:
        return "Ошибка API распознавания речи."
    except Exception as e:
        logging.error(f"Ошибка обработки аудио: {e}")
        return "Произошла ошибка при обработке аудио."
    finally:
        for temp_file in [file_path, temp_wav]:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    logging.error(f"Не удалось удалить временный файл {temp_file}: {e}")


@dp.message(Command("start"))
async def handle_start(message: Message):
    """Отвечает на команду /start."""
    await message.reply("Привет! Сосал?")

@dp.message(F.voice)
async def handle_voice(message: Message):
    """Обрабатывает голосовые сообщения."""
    download_path = tempfile.mktemp(suffix=".ogg")
    await bot.download(message.voice, destination=download_path)
    text = await transcribe_audio(download_path)
    await message.reply(f"<b>Расшифровка:</b>\n\n<i>{text}</i>")

@dp.message(F.video_note)
async def handle_video_note(message: Message):
    """Обрабатывает видео-кружочки."""
    download_path = tempfile.mktemp(suffix=".mp4")
    await bot.download(message.video_note, destination=download_path)
    text = await transcribe_audio(download_path)
    await message.reply(f"<b>Расшифровка кружочка:</b>\n\n<i>{text}</i>")

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
    print("Бот запущен и готов к работе!")

async def main():
    """Основная функция для запуска бота."""
    dp.startup.register(on_startup)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())