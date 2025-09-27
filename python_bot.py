import os
import tempfile
import uuid
import speech_recognition as sr
from pydub import AudioSegment
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"  # Вставь токен от @BotFather
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

def transcribe_audio(file_path):
    recognizer = sr.Recognizer()
    temp_wav = None
    try:
        audio = AudioSegment.from_file(file_path)
        unique_id = str(uuid.uuid4())
        temp_wav = os.path.join(tempfile.gettempdir(), f'temp_audio_{unique_id}.wav')
        audio.export(temp_wav, format='wav')
        
        with sr.AudioFile(temp_wav) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='ru-RU')
            return text
    except sr.UnknownValueError:
        return "Не удалось распознать речь."
    except sr.RequestError:
        return "Ошибка API. Проверь лимиты Google STT."
    except Exception as e:
        return f"Ошибка обработки: {str(e)}"
    finally:
        for temp_file in [file_path, temp_wav]:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except PermissionError:
                    print(f"Не удалось удалить {temp_file}")

@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    file = await bot.get_file(message.voice.file_id)
    unique_id = str(uuid.uuid4())
    file_path = f"voice_{unique_id}.ogg"
    await file.download_to_drive(file_path)
    
    text = transcribe_audio(file_path)
    await message.reply(f"Расшифровка: {text}")

@dp.message_handler(content_types=types.ContentType.VIDEO_NOTE)
async def handle_video_note(message: types.Message):
    file = await bot.get_file(message.video_note.file_id)
    unique_id = str(uuid.uuid4())
    file_path = f"video_note_{unique_id}.mp4"
    await file.download_to_drive(file_path)
    
    text = transcribe_audio(file_path)
    await message.reply(f"Расшифровка: {text}")

async def main():
    dp.startup.register(lambda: print("Бот запущен! Отправь голосовое или кружочек."))
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())