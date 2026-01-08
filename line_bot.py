import os, time, re, base64, json
import requests
import slackweb
import sqlite3
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage, ImageMessage
from linebot.v3.messaging import MessagingApi, MessagingApiBlob, Configuration, ApiClient
from linebot.v3.messaging.models import ReplyMessageRequest, PushMessageRequest, TextMessage
from datetime import datetime
from pathlib import Path

app = Flask(__name__)

# トークンを読み込む
load_dotenv()
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
GYAZO_ACCESS_TOKEN = os.getenv("GYAZO_ACCESS_TOKEN")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")

# LINE Bot APIの設定
configuration = Configuration(access_token=os.environ["LINE_BOT_API"])
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)
messaging_api_blob = MessagingApiBlob(api_client)
# v2 LineBotApi (simpler message helpers)
line_bot_api = LineBotApi(os.environ["LINE_BOT_API"])  # Added
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET_TOKEN"])

def reply_text(reply_token: str, text: str):
    """テキスト返信（reply_tokenは1回だけ有効）。まずv2、失敗時にv3。"""
    sanitized = "" if text is None else str(text)
    if not sanitized.strip():
        sanitized = "応答が空でした。もう一度お試しください。"
    try:
        line_bot_api.reply_message(reply_token, TextSendMessage(text=sanitized))
        return
    except Exception as e:
        try:
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=sanitized)]
                )
            )
        except Exception as e2:
            try:
                slack(f"reply_text error: {e} / v3 fallback: {e2}")
            except Exception:
                pass

def _extract_blob_content(resp):
    """LINE v3 blob APIのレスポンスからバイト列とMIMEを取り出す。"""
    default_mime = "image/jpeg"
    mime = default_mime
    data = None

    # ヘッダ取得
    if hasattr(resp, "headers") and isinstance(resp.headers, dict):
        mime = resp.headers.get("Content-Type", default_mime)

    # データ取り出し
    if hasattr(resp, "data") and resp.data:
        data = resp.data if isinstance(resp.data, (bytes, bytearray)) else bytes(resp.data)
    elif hasattr(resp, "iter_content"):
        data = b"".join(resp.iter_content(chunk_size=1024))
    elif hasattr(resp, "read"):
        data = resp.read()
    elif hasattr(resp, "content"):
        data = resp.content if isinstance(resp.content, (bytes, bytearray)) else bytes(resp.content)
    elif isinstance(resp, (bytes, bytearray)):
        data = bytes(resp)

    return data, mime

RECENT_IMAGE_TTL = 120  # seconds
recent_images = {}  # user_id -> {"data": bytes, "ts": float}

def slack(text):
  slack = slackweb.Slack(url=SLACK_WEBHOOK)
  slack.notify(text=text, username="raspi-bot", icon_emoji=":raspberrypi:", mrkdwn=True)


# response_id保存用のデータベース
def save_response_id(user_id: str, response_id: str):
    # 関数内で接続を作成
    conn = sqlite3.connect('chatbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
    cur = conn.cursor()
    
    # テーブルがなければ作成
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        user_id     TEXT PRIMARY KEY,
        response_id TEXT NOT NULL,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cur.execute("""
    INSERT OR REPLACE INTO sessions (user_id, response_id, updated_at)
    VALUES (?, ?, ?)
    """, (user_id, response_id, datetime.now()))
    conn.commit()
    conn.close()

def get_response_id(user_id: str) -> str | None:
    # 関数内で接続を作成
    conn = sqlite3.connect('chatbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
    cur = conn.cursor()
    
    # テーブルがなければ作成
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        user_id     TEXT PRIMARY KEY,
        response_id TEXT NOT NULL,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cur.execute("SELECT response_id FROM sessions WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


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
    user_id = event.source.user_id
    user_text = event.message.text

    slack("line: " + user_text + "\n")

    # 直近画像の有効期限管理
    img_entry = recent_images.get(user_id)
    if img_entry and (time.time() - img_entry["ts"] > RECENT_IMAGE_TTL):
        recent_images.pop(user_id, None)
        img_entry = None

    try:
        if img_entry:
            # 画像＋プロンプトをOpenAI Visionへ
            image_b64 = base64.b64encode(img_entry["data"]).decode("utf-8")
            mime = img_entry.get("mime", "image/jpeg")
            image_data_url = f"data:{mime};base64,{image_b64}"
            vision_input = [
                {
                    "role": "user",
                    "content": [
                {
                    "type": "input_text",
                            "text": (
                                "以下の画像を: {prompt}\n"
                                "- 箇条書きで説明\n"
                                "- 画像内の文字は抽出して明示\n"
                                "- 日本語で回答"
                            ).format(prompt=user_text)
                },
                {
                    "type": "input_image",
                            "image_url": image_data_url  # base64 data URL をそのまま渡す
                    }
                    ]
                }
            ]
            response = client.responses.create(
                model="gpt-5.2",
                reasoning={"effort": "medium"},
                input=vision_input,
                stream=False,
                store=True,
                instructions="必ず日本語で、箇条書きで回答してください。"
            )
            recent_images.pop(user_id, None)
            # ユーザIDごとに response_id を更新
            save_response_id(user_id, response.id)
            result = response.output_text
            reply_text(event.reply_token, result)
        else:
            # response_id使用（テキストのみ）
            prev_response_id = get_response_id(user_id)
            response = client.responses.create(
                model="gpt-5.2",
                reasoning={"effort": "medium"},
                tools=[{"type": "web_search"}],
                previous_response_id=prev_response_id,
                input=user_text,
                stream=False,
                store=True,
                instructions="""あなたは優秀なAIアシスタントです。回答は必ず日本語で行います。
                ユーザーの要求が画像生成に関連する場合は、必ず「画像生成が必要です」というフレーズを含めてください。
                Web検索が必要な場合は、検索結果に確信が得られるまで検索してください。
                それ以外の場合は通常の会話として応答してください。
                **強調** という強調表現は禁止です。
                Powered by GPT-5.2
                """
            )
            # ユーザIDごとに response_id を更新
            save_response_id(user_id, response.id)
            result = response.output_text

            # 画像生成が必要かどうかを判断
            if "画像生成が必要です" in result:
                # If 1-on-1 chat, show loading animation instead of text
                if event.source.type == "user":
                    start_loading(event.source.user_id, seconds=60)
                else:
                    # fallback for group/room where loading animation is unsupported
                    reply_text(event.reply_token, "画像を生成中です。少々お待ちください")
                # 画像生成の指示から「画像生成が必要です」を削除
                prompt = result.replace("画像生成が必要です", "").strip()
                result = create_image(prompt, event.reply_token)
                if result == "success":
                    upload_file_url = upload_to_gyazo('/home/pi/images/image.png')
                    if event.source.type == "user":
                        line_bot_api.push_message(
                            to=event.source.user_id,
                            messages=[ImageSendMessage(original_content_url=upload_file_url,
                                                        preview_image_url=upload_file_url)]
                        )
                    elif event.source.type == "group":
                        line_bot_api.push_message(
                            to=event.source.group_id,
                            messages=[ImageSendMessage(original_content_url=upload_file_url,
                                                        preview_image_url=upload_file_url)]
                        )
                    elif event.source.type == "room":
                        line_bot_api.push_message(
                            to=event.source.room_id,
                            messages=[ImageSendMessage(original_content_url=upload_file_url,
                                                        preview_image_url=upload_file_url)]
                        )
                    slack("line: 画像を出力しました")
            else:
                # 通常の会話として応答
                reply_text(event.reply_token, result)

    except Exception as e:
        reply_text(event.reply_token, f"エラーが発生しました: {e}")
        slack(f"line error: {e}")


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    try:
        # v3 blob API推奨
        content = messaging_api_blob.get_message_content(message_id=event.message.id)
        img_bytes, mime = _extract_blob_content(content)
        if not img_bytes:
            raise RuntimeError("画像データの取得に失敗しました。")
        recent_images[user_id] = {"data": img_bytes, "ts": time.time(), "mime": mime}
        reply_text(event.reply_token, "画像を受け取りました。解析したい指示をテキストで送ってください。")
    except Exception as e:
        reply_text(event.reply_token, f"画像の受信に失敗しました: {e}")
        slack(f"画像受信エラー: {e}")




### gpt-image-1 ###
def create_image(prompt, reply_token):
    from openai import OpenAI
    import os
    from pathlib import Path

    client = OpenAI()
    model = "gpt-image-1"
    size = "1536x1024"
    n = 1

    try:
        # 画像保存用のディレクトリを作成
        image_dir = Path("/home/pi/images")
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / "image.png"

        result = client.images.generate(
            model = model,
            prompt = prompt,
            n = n,
        )

        image_base64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)

        # Save the image to a file
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        return "success"

    except Exception as e:
        error_message = str(e)
        # エラーメッセージの抽出を試みる
        try:
            if "'message': '" in error_message:
                error_message = re.search(r"'message': '(.*?)'", error_message).group(1)
        except:
            pass  # エラーメッセージの抽出に失敗した場合は元のエラーメッセージを使用

        reply_text(reply_token, f"画像生成中にエラーが発生しました: {error_message}")
        slack(f"画像生成エラー: {error_message}")
        return "error"

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

# helper: start loading animation
def start_loading(chat_id: str, seconds: int = 20):
    """Display typing/loading animation for up to `seconds` seconds (5-60)."""
    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ['LINE_BOT_API']}"
    }
    data = {
        "chatId": chat_id,
        "loadingSeconds": max(5, min(seconds, 60))
    }
    try:
        requests.post(url, headers=headers, json=data, timeout=3)
    except Exception:
        pass  # ignore errors; just best-effort

if __name__ == "__main__":
    app.run()
