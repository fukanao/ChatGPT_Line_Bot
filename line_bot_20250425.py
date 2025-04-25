import os, time, re
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


    # text内に"を描いて"もしくは”描いて”が含まれる場合、描いて以降を削除
    if "を描いて" in user_text or "描いて" in user_text:
        # パターンにマッチする部分から後ろを削除
        # パターン: "を描いて" もしくは "描いて" 以降のテキストを削除
        pattern = r'を?描いて.*$'
        trimmed_text = re.sub(pattern, '', user_text, flags=re.DOTALL)
        image_url = create_image(trimmed_text)
        image_filename = download_dalle_image(image_url)
        #print(image_filename)
        #upload_file_url = upload_google_drive(image_filename)
        upload_file_url = upload_to_gyazo(image_filename)

        #line_bot_api.reply_message(event.reply_token, TextSendMessage(text=upload_file_url))
        line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=upload_file_url,
            preview_image_url=upload_file_url))


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

            '''
            # OpenAI Assistant + threads使用
            message = client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_text
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
            '''

            '''
            # 辞書形式で会話保持
            # 初回の場合はシステムメッセージを含めて初期化（システムメッセージは常に保持）
            if user_id not in conversation_history:
                conversation_history[user_id] = [
                    {"role": "system", "content": "あなたは有能なアシスタントです。"}
                ]

            # ユーザの発言を会話履歴に追加
            conversation_history[user_id].append({"role": "user", "content": user_text})

            # システムメッセージを除いたユーザ／アシスタントの会話部分が最大 MAX_TURNS * 2 件になるように制限
            # 全体で MAX_TURNS * 2 + 1 (システムメッセージ分) 件とする
            max_messages = MAX_TURNS * 2 + 1
            while len(conversation_history[user_id]) > max_messages:
                # システムメッセージ (インデックス0) は削除せず、古いユーザ/アシスタントのメッセージを削除
                conversation_history[user_id].pop(1)

            # responses API使用
            response = client.responses.create(
                model="gpt-4o",
                tools=[{"type": "web_search_preview"}],
                #input=text
                input=conversation_history[user_id],
            )

            result = response.output_text

            # アシスタントの返答を会話履歴に追加
            conversation_history[user_id].append({"role": "assistant", "content": result})

            # 再度、履歴が上限を超えていれば削除
            while len(conversation_history[user_id]) > max_messages:
                conversation_history[user_id].pop(1)

            '''

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





### dalle ###
def create_image(prompt):
    #OPENAI_KEY = os.environ["OPENAI_API_KEY"]
    from openai import OpenAI
    client = OpenAI()
    model = "dall-e-3"
    prompt = prompt
    #size = "512x512"
    size = "1024x1792"
    quolity = "standard"
    n = 1

    try:
        response = client.images.generate(
            model = model,
            prompt = prompt,
            #size = size,
            #quolity = quolity,
            n = n,
        )
        image_url = response.data[0].url

    except Exception as e:
        error_message = re.search(r"'message': '(.*?)'", str(e)).group(1)
        #print("#186", error_message)
        return

    #image_url = response.data[0].url

    return(image_url)


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

    return image_filename

def upload_to_gyazo(image_file_name):
    url = 'https://upload.gyazo.com/api/upload'
    with open("images/"+image_file_name, 'rb') as image_file:
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
            print(response_data['url'])
            return response_data['url']
        except json.JSONDecodeError:
            print("JSON decode error: " + response.text)  # エラー内容を明確に表示
'''
def upload_google_drive(image_file_name):
    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()
    drive = GoogleDrive(gauth)

    # imagesディレクトリのIDを取得または作成
    images_folder_name = 'images'
    images_folder_id = None

    folder_list = drive.ListFile({'q': "title='" + images_folder_name + "' and mimeType='application/vnd.google-apps.folder' and trashed=false"}).GetList()
    if folder_list:
        images_folder_id = folder_list[0]['id']
    else:
        images_folder = drive.CreateFile({'title': images_folder_name, 'mimeType': 'application/vnd.google-apps.folder'})
        images_folder.Upload()
        images_folder_id = images_folder['id']

    # 画像ファイルをアップロード
    #image_file_name = 'test.jpg'
    f = drive.CreateFile({'title': image_file_name, 'mimeType': 'image/jpeg', 'parents': [{'id': images_folder_id}]})
    f.SetContentFile("images/" + image_file_name)
    f.Upload()

    def convert_url(url):
        file_id = re.findall(r'/d/([a-zA-Z0-9-_]+)', url)[0]
        converted_url = f'http://drive.google.com/uc?export=view&id={file_id}'
        return converted_url

    alternateLink = f['alternateLink']
    converted_link = convert_url(alternateLink)

    return converted_link
'''







if __name__ == "__main__":
    app.run()
