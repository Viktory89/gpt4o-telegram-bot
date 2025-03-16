import openai
import telebot
import os
import requests
from flask import Flask, request
from io import BytesIO
from pdfminer.high_level import extract_text
import pandas as pd
from PIL import Image
from threading import Thread
import queue

openai.api_key = os.getenv("OPENAI_API_KEY")
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
app = Flask(__name__)

# Глобальная история диалога
chat_history = []

# Очередь сообщений (асинхронная обработка)
message_queue = queue.Queue()

# Обработка очереди в фоне
def process_messages():
    while True:
        item = message_queue.get()
        if item['type'] == 'text':
            handle_text_message(item['message'])
        message_queue.task_done()

worker_thread = Thread(target=process_messages)
worker_thread.daemon = True
worker_thread.start()

@bot.message_handler(commands=['start'])
def start_dialog(message):
    bot.send_message(message.chat.id, "Привет! Я GPT-бот. Готов к диалогу 😊")

@bot.message_handler(commands=['clear'])
def clear_history(message):
    global chat_history
    chat_history = []
    bot.send_message(message.chat.id, "История диалога очищена ✅")

@bot.message_handler(content_types=['text'])
def enqueue_text(message):
    message_queue.put({'type': 'text', 'message': message})

def handle_text_message(message):
    global chat_history
    chat_history.append({"role": "user", "content": message.text})

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=chat_history
        )
        reply = response.choices[0].message["content"]
        chat_history.append({"role": "assistant", "content": reply})
        bot.send_message(message.chat.id, reply)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка OpenAI: {e}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/{file_info.file_path}"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Посмотри на это изображение и скажи, что на нём."},
                        {"type": "image_url", "image_url": {"url": file_url}}
                    ]
                }
            ]
        )
        reply = response.choices[0].message["content"]
        bot.send_message(message.chat.id, reply)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка анализа изображения: {e}")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    try:
        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/{file_info.file_path}"
        file_name = message.document.file_name.lower()
        file_data = requests.get(file_url).content

        if file_name.endswith('.pdf'):
            text = extract_text(BytesIO(file_data))
            bot.send_message(message.chat.id, f"Текст из PDF:\n\n{text[:4000]}")

        elif file_name.endswith('.xlsx') or file_name.endswith('.xls'):
            df = pd.read_excel(BytesIO(file_data))
            bot.send_message(message.chat.id, f"Таблица загружена. Первые строки:\n\n{df.head().to_string()}")

        elif file_name.endswith('.csv'):
            df = pd.read_csv(BytesIO(file_data))
            bot.send_message(message.chat.id, f"CSV-файл загружен. Первые строки:\n\n{df.head().to_string()}")

        else:
            bot.send_message(message.chat.id, "Формат файла не поддерживается ❌")

    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при обработке файла: {e}")

@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'ok', 200
    return 'GPT Telegram Webhook активен!', 200

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=os.getenv("WEBHOOK_URL"))
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
