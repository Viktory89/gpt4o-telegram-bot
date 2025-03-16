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

# История сообщений (для одного пользователя)
chat_history = []

# Очередь сообщений
message_queue = queue.Queue()

# Фоновый обработчик
def process_messages():
    while True:
        item = message_queue.get()
        if item['type'] == 'text':
            handle_text_message(item['message'])
        message_queue.task_done()

Thread(target=process_messages, daemon=True).start()

# Команды
@bot.message_handler(commands=['start'])
def start_dialog(message):
    bot.send_message(message.chat.id, "Привет! Я GPT-бот. Пиши свои вопросы или присылай файлы 📎")

@bot.message_handler(commands=['clear'])
def clear_history(message):
    global chat_history
    chat_history = []
    bot.send_message(message.chat.id, "История диалога очищена ✅")

# Тексты
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
        bot.send_message(message.chat.id, f"⚠ Ошибка OpenAI: {e}")

# Фото (анализ через GPT-4o vision)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/{file_info.file_path}"

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Посмотри на это изображение и опиши его."},
                        {"type": "image_url", "image_url": {"url": file_url}}
                    ]
                }
            ]
        )
        reply = response.choices[0].message["content"]
        bot.send_message(message.chat.id, reply)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠ Ошибка при анализе изображения: {e}")

# Документы
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
            bot.send_message(message.chat.id, f"📄 Текст из PDF:\n\n{text[:4000]}")

        elif file_name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(BytesIO(file_data))
            bot.send_message(message.chat.id, f"📊 Excel загружен:\n\n{df.head().to_string()}")

        elif file_name.endswith('.csv'):
            df = pd.read_csv(BytesIO(file_data))
            bot.send_message(message.chat.id, f"📊 CSV загружен:\n\n{df.head().to_string()}")

        elif file_name.endswith(('.png', '.jpg', '.jpeg')):
            # Анализ изображения как document через vision
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Что изображено на этом PNG/JPG?"},
                            {"type": "image_url", "image_url": {"url": file_url}}
                        ]
                    }
                ]
            )
            reply = response.choices[0].message["content"]
            bot.send_message(message.chat.id, reply)

        else:
            bot.send_message(message.chat.id, "⚠ Формат файла не поддерживается.")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠ Ошибка при обработке файла: {e}")

# Webhook-обработчик
@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        update = telebot.types.Update.de_json(request.data.decode('utf-8'))
        bot.process_new_updates([update])
        return 'ok', 200
    return 'GPT Webhook live ✅', 200

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=os.getenv("WEBHOOK_URL"))
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
