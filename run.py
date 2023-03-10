import yaml
import os
import openai
import math
import requests
from urllib.parse import quote
import pprint
import time
import sys
import traceback

config = yaml.load(open('config.yml'), Loader=yaml.FullLoader)

openai.organization = config['chat_gpt']['organization']
openai.api_key = config['chat_gpt']['api_key']
# print(openai.Model.list())

def telegram_fetch(message: str) -> bool:
    message = str(message)

    # updates and chatId https://api.telegram.org/bot<YourBOTToken>/getUpdates
    # For \n use %0A message = message.replace(/\n/g, "%0A")
    url = (
        "https://api.telegram.org/bot"
        + config["telegram"]["bot_key"]
        + "/sendMessage?chat_id="
        + config["telegram"]["chat_id"]
        + "&text="
        + quote(message)
    )

    try:
        response = (requests.get(url)).json()
        return response["ok"]
    except:
        return False

def send_telegram(message: str) -> None:
    packages_remaining = [message]
    max_messages_num = 40
    while len(packages_remaining) > 0 and max_messages_num > 0:
        curr_package = packages_remaining.pop(0)
        message_sent = telegram_fetch(curr_package)
        if message_sent:
            max_messages_num -= 1
        if not message_sent:
            if len(curr_package) < 10:
                telegram_fetch("Telegram failed")
                break
            num_of_chars_first = math.ceil(len(curr_package) / 2)
            first_package = curr_package[0:num_of_chars_first]
            second_package = curr_package[num_of_chars_first : len(curr_package)]

            packages_remaining.insert(0, second_package)
            packages_remaining.insert(0, first_package)
    if max_messages_num == 0:
        telegram_fetch("Sending failed. Too many messages sent.")

def on_error_send_traceback(log_func):
    def on_error_send_traceback_decorator(function):
        def wrapper_function(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except Exception as err:
                # traceback.print_tb(err.__traceback__)
                etype, value, tb = sys.exc_info()
                max_stack_number = 300
                traceback_string = ''.join(traceback.format_exception(etype, value, tb, max_stack_number))
                log_func('Exception in ' + function.__name__ + '\n' + traceback_string)

        return wrapper_function
    return on_error_send_traceback_decorator

@on_error_send_traceback(send_telegram)
def ask_chat_gpt(question):
    try:
        answer = openai.Completion.create(
            model=config['chat_gpt']['model'],
            prompt=question,
            max_tokens=int(config['chat_gpt']['max_tokens_per_request']),
            temperature=0
        )
        text = answer['choices'][0]['text']
        # new line in csv file with date, time, question, answer
        with open('chat_gpt_log.csv', 'a') as f:
            # remove new line characters
            log_text = text.replace('\n', ' ')
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")},{question},{log_text}')
        return text
    except Exception as err:
        with open('chat_gpt_log.csv', 'a') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")},{question},{"ChatGPT failed"}')
        raise err

def poll_telegram():
    url = (
        "https://api.telegram.org/bot"
        + config["telegram"]["bot_key"]
        + "/getUpdates"
    )
    response = requests.get(url).json()
    
    if response["ok"]:
        return response["result"]

    telegram_fetch("Poll failed")

def latest_telegram_messages():
    response = poll_telegram()
    all_messages = [m["message"] for m in response if "message" in m]
    all_text_messages = [m for m in all_messages if "text" in m]
    chat_messages = [m for m in all_text_messages if int(m["chat"]["id"]) == int(config["telegram"]["chat_id"])]
    time_id_text = [(m["date"], m["message_id"], m["text"]) for m in chat_messages]
    time_id_text.sort(key=lambda x: x[0], reverse=True)
    return time_id_text

latest_message_id = None
while True:
    time.sleep(int(config['telegram']['polling_interval_in_seconds']))
    messages = latest_telegram_messages()
    if len(messages) == 0 or messages[0][1] == latest_message_id:
        continue
    latest_message_id = messages[0][1]
    text = messages[0][2]
    send_telegram(ask_chat_gpt(text))


