import os, time
from dotenv import load_dotenv
from openai import OpenAI
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from collections import defaultdict

app = Flask(__name__)

# トークンを読み込む
load_dotenv()
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")


line_bot_api = LineBotApi(os.environ["LINE_BOT_API"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET_TOKEN"])

# assitantAPI対応

def load_user_thread_pairs(filename):
    """ ファイルからユーザーIDとスレッドIDのペアを読み込み、辞書として返す """
    user_thread_pairs = {}
    with open(filename, 'r') as file:
        for line in file:
            user_id, thread_id = line.strip().split(',')
            user_thread_pairs[user_id] = thread_id
    return user_thread_pairs

def save_user_thread_pair(filename, user_id, thread_id):
    """ ユーザーIDとスレッドIDのペアをファイルに保存する """
    with open(filename, 'a') as file:
        file.write(f"{user_id},{thread_id}\n")

def get_or_create_thread(client, user_thread_pairs, user_id, filename):
    """ ユーザーIDに基づいてスレッドIDを取得または作成する """
    if user_id in user_thread_pairs:
        return user_thread_pairs[user_id]
    else:
        # 新しいスレッドを作成（APIの仕様に応じて変更する必要あり）
        new_thread = client.beta.threads.create()
        new_thread_id = new_thread.id
        user_thread_pairs[user_id] = new_thread_id
        save_user_thread_pair(filename, user_id, new_thread_id)
        return new_thread_id

filename = 'user_thread_pairs.txt'
user_thread_pairs = load_user_thread_pairs(filename)

client = OpenAI(api_key=OPENAI_KEY)








#@app.route("/callback", methods=['POST'])
@app.route("/", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global now_str

    user_id = event.source.user_id
    text = event.message.text

    # thread_id取得
    thread_id = get_or_create_thread(client, user_thread_pairs, user_id, filename)

    # アシスタント指定(アイ)
    assistant = client.beta.assistants.retrieve("asst_2wEbwn4xyYDy6F06jJSkJNa5")

    # thread指定
    thread = client.beta.threads.retrieve(thread_id)

    try:
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=text
        )
        # 実行を作成
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id,
        )

        while run.status in ['queued', 'in_progress', 'cancelling']:
            time.sleep(1) # Wait for 1 second
            run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
            )

            if run.status == 'completed':
                messages = client.beta.threads.messages.list(
                thread_id=thread.id
            )
                break
            else:
                print(run.status)

                    # メッセージリストから回答を取得
        for message in messages.data:
            # アシスタントによるメッセージを探す
            if message.role == "assistant":
                # メッセージの内容を表示
                result = message.content[0].text.value
                break

        # Lineに回答を返す
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))


    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=str(e)))
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text='エラーが発生しました。'))

    """
    else:
        print("画像削除した場合'text' key not found in the event data.")
        return
    """


if __name__ == "__main__":
    app.run()
