import os, time, re, base64, json
import requests
import slackweb
from dotenv import load_dotenv
from openai import OpenAI
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage

from pathlib import Path

app = Flask(__name__)

# トークンを読み込む
load_dotenv()
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
GYAZO_ACCESS_TOKEN = os.getenv("GYAZO_ACCESS_TOKEN")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")


line_bot_api = LineBotApi(os.environ["LINE_BOT_API"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET_TOKEN"])

def slack(text):
  slack = slackweb.Slack(url=SLACK_WEBHOOK)
  slack.notify(text=text, username="raspi-bot", icon_emoji=":raspberrypi:", mrkdwn=True)

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

# 各ユーザごとの会話履歴を保持する辞書
# key: user_id, value: 会話履歴のリスト
#conversation_history = {}

# response_idをユーザごとに保持
response_ids = {}



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
    # response_ids使用
    global response_ids

    user_id = event.source.user_id
    user_text = event.message.text

    # thread_id取得
    #thread_id = get_or_create_thread(client, user_thread_pairs, user_id, filename)

    # アシスタント指定
    #assistant = client.beta.assistants.retrieve("asst_BtQb6ntcebFPeEtcVfdMnyzB")
    # thread指定
    #thread = client.beta.threads.retrieve(thread_id)

    # ユーザ／アシスタントの会話はシステムメッセージを除いて最新の3ターン（＝ユーザとアシスタント各3ターン分）に制限
    #MAX_TURNS = 3

    slack("line: " + user_text + "\n")


    # text内に"を描いて"もしくは"描いて"が含まれる場合、描いて以降を削除
    if "を描いて" in user_text or "描いて" in user_text:
        #print("#111 image start")
        # パターンにマッチする部分から後ろを削除
        # パターン: "を描いて" もしくは "描いて" 以降のテキストを削除
        pattern = r'を?描いて.*$'
        trimmed_text = re.sub(pattern, '', user_text, flags=re.DOTALL)

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="最大3分待っててね"))
        result = create_image(trimmed_text, event.reply_token)
        if result == "success":
            upload_file_url = upload_to_gyazo('/home/pi/images/image.png')
            # ここでevent.source.typeを判定
            if event.source.type == "user":
                line_bot_api.push_message(event.source.user_id, ImageSendMessage(
                    original_content_url=upload_file_url,
                    preview_image_url=upload_file_url))
            elif event.source.type == "group":
                line_bot_api.push_message(event.source.group_id, ImageSendMessage(
                    original_content_url=upload_file_url,
                    preview_image_url=upload_file_url))
            elif event.source.type == "room":
                line_bot_api.push_message(event.source.room_id, ImageSendMessage(
                    original_content_url=upload_file_url,
                    preview_image_url=upload_file_url))
            slack("line: 画像を出力しました")


    # text内に"を描いて"が含まれない場合（通常会話）
    else:
        try:
            # response_id使用
            # ユーザIDに対応する前回の response_id をテーブルから取得（存在しなければ None）
            prev_response_id = response_ids.get(user_id)

            response = client.responses.create(
                model="gpt-4.1",
                tools=[{"type": "web_search_preview"}],
                previous_response_id=prev_response_id,
                input=user_text,
                instructions="あなたは優秀なAIアシスタントです。回答は必ず日本語で行います。"
            )
            # ユーザIDごとに response_id を更新
            response_ids[user_id] = response.id
            result = response.output_text

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





### gpt-image-1 ###
def create_image(prompt, reply_token):
    #OPENAI_KEY = os.environ["OPENAI_API_KEY"]
    from openai import OpenAI
    client = OpenAI()
    model = "gpt-image-1"
    prompt = prompt
    #size = "1024x1024"
    size = "1536x1024"
    n = 1

    try:
        result = client.images.generate(
            model = model,
            prompt = prompt,
            n = n,
        )

        image_base64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)

        # Save the image to a file
        with open("/home/pi/images/image.png", "wb") as f:
            f.write(image_bytes)

        #print("#183 create_image success")
        return "success"

    except Exception as e:
        error_message = re.search(r"'message': '(.*?)'", str(e)).group(1)
        #print("#259", error_message)
        line_bot_api.reply_message(reply_token, TextSendMessage(text=error_message))
        slack("#191 "+ str(e))
        return "error"
    return

def download_dalle_image(url):
    img_data = requests.get(
        url,
        allow_redirects=True,
        stream=True,
    ).content

    # image_filename取得
    pattern = r"img-[a-zA-Z0-9]+\.png"
    match = re.search(pattern, url)

    if match:
        image_filename = match.group()
        #print("Image filename:", image_filename)
    else:
        image_filename = "noname_image.png"
        #print("No image filename found in the URL.")

    # image_file保存
    with open(Path(f"./images/{image_filename}").absolute(), "wb") as f:
        f.write(img_data)

    #print("#215 download_image") 
    return image_filename

def upload_to_gyazo(image_file_name):
    url = 'https://upload.gyazo.com/api/upload'
    with open("/home/pi/images/image.png", 'rb') as image_file:
        files = {
            'imagedata': ('image.png', image_file)
            #'imagedata': ('image.jpeg', image_file) #pngじゃないとダメだった
        }
        data = {
            'access_token': GYAZO_ACCESS_TOKEN
        }
        response = requests.post(url, files=files, data=data)
        try:
            response_data = response.json()
            #print("#232 upload gyazo" + response_data['url'])
            return response_data['url']
        except json.JSONDecodeError:
            print("JSON decode error: " + response.text)  # エラー内容を明確に表示


if __name__ == "__main__":
    app.run()
