import openai
import telebot
import os
import requests
from io import BytesIO
from pdfminer.high_level import extract_text
import pandas as pd
from PIL import Image

# Загружаем API-ключи из переменных окружения
openai.api_key = os.getenv("OPENAI_API_KEY")
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

# Словарь для хранения истории чатов (для 1 пользователя)
chat_history = []

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    """ Обрабатывает текстовые сообщения и сохраняет контекст """
    global chat_history

    chat_history.append({"role": "user", "content": message.text})

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=chat_history
    )

    reply = response.choices[0].message["content"]
    chat_history.append({"role": "assistant", "content": reply})

    bot.send_message(message.chat.id, reply)

@bot.message_handler(content_types=['document', 'photo'])
def handle_file(message):
    """ Обрабатывает отправленные файлы (PDF, Excel, Фото) """
    file_id = message.document.file_id if message.document else message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/{file_info.file_path}"
    
    file_data = requests.get(file_url).content
    file_extension = file_info.file_path.split('.')[-1].lower()

    if file_extension in ['png', 'jpg', 'jpeg']:
        # Обработка изображений
        image = Image.open(BytesIO(file_data))
        bot.send_message(message.chat.id, "Я получил фото, но пока не умею его анализировать 😔")
    
    elif file_extension in ['pdf']:
        # Обработка PDF
        pdf_text = extract_text(BytesIO(file_data))
        bot.send_message(message.chat.id, f"Вот текст из PDF:\n\n{pdf_text[:4000]}")

    elif file_extension in ['xls', 'xlsx', 'csv']:
        # Обработка таблиц
        df = pd.read_excel(BytesIO(file_data)) if 'xls' in file_extension else pd.read_csv(BytesIO(file_data))
        bot.send_message(message.chat.id, f"Таблица загружена! Первые строки:\n\n{df.head().to_string()}")

    else:
        bot.send_message(message.chat.id, "Формат файла не поддерживается ❌")

@bot.message_handler(commands=['clear'])
def clear_chat(message):
    """ Очищает историю диалога """
    global chat_history
    chat_history = []
    bot.send_message(message.chat.id, "История диалога очищена ✅")

bot.polling()
