import os
import tempfile
import uuid
import speech_recognition as sr
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext
from pydub import AudioSegment


TOKEN = ''

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
                    print(f"Не удалось удалить {temp_file} (файл заблокирован, но это ок)")


async def handle_message(update: Update, context: CallbackContext):
    message = update.message
    file_path = None
    
    try:
        if message.voice:  # Голосовое сообщение
            file = await context.bot.get_file(message.voice.file_id)
            # Уникальное имя для скачанного файла
            unique_id = str(uuid.uuid4())
            file_path = f"voice_{unique_id}.ogg"
            await file.download_to_drive(file_path)
        elif message.video_note:  # кружочек
            file = await context.bot.get_file(message.video_note.file_id)
            unique_id = str(uuid.uuid4())
            file_path = f"video_note_{unique_id}.mp4"
            await file.download_to_drive(file_path)
        
        if file_path:
            text = transcribe_audio(file_path)
            await message.reply_text(f"Расшифровка: {text}")
    except Exception as e:
        await message.reply_text(f"Ошибка: {str(e)}")
        print(f"Ошибка в handle_message: {e}")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.VOICE | filters.VIDEO_NOTE, handle_message))
    print("Бот запущен! Отправь голосовое или кружочек.")
    application.run_polling()

if __name__ == '__main__':
    main()