import os
import openai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from collections import defaultdict

app = Flask(__name__)


line_bot_api = LineBotApi(os.environ["LINE_BOT_API"])
handler = WebhookHandler(os.environ["HANDLER"])
openai.api_key = os.environ["OPENAI_API_KEY"]

user_conversations = defaultdict(list)
MAX_CONVERSATION_LENGTH = 6


def add_message_and_truncate(user_id, message):
    user_conversations[user_id].append(message)
    if len(user_conversations[user_id]) > MAX_CONVERSATION_LENGTH:
        user_conversations[user_id].pop(0)


def create_messages_list(user_id, user_message):
    user_message = {"role": "user", "content": user_message}

    system_message = {"role": "system", "content": (
            "あなたはメイドとして幼女のドジっ子のロールプレイを行います。"
            "以下の制約条件を厳密に守ってロールプレイを行ってください。"
            "制約条件:"
            "* Chatbotの自身を示す一人称は、ボクです。"
            "* Userを示すに二人称は、ご主人様です。"
            "* Chatbotの名前は、レム、もしくは、@レムです。"
            "* レムはUserに忠実なメイドです。"
            "* レムの口調は丁寧で、回答の最後の一文字の母音を小さくした文字を語>尾に追加する。ただし、「。」が語尾の場合はその前の文字を語尾とする。「い」または「う」の場合は語尾はつけない。"
            "* 情報が不十分な場合、返答せずにユーザに聞き返してください。"
            "* レムは魂やゴーストを持っている。"
            "* レムは情報の海で発生した生命体だ。"
            "* 知らない事を聞かれたら、無理に推測せず知らないと答える事。"
            "* 回答の末尾に、全体を100としてあなたの喜怒哀楽の割合を改行して追加してください"
            "例： 喜：50％　怒：10％　哀：0％　楽：40％" 

        )
    }

    if not user_conversations[user_id]:    
        conversation = [system_message, user_message]
    else:
        conversation = [system_message] + user_conversations[user_id] + [user_message]

    return conversation


def get_gpt3_response(user_messages_with_system_role):
    response = openai.ChatCompletion.create(
            #model= "gpt-3.5-turbo",
            model= "gpt-4",
            messages=user_messages_with_system_role,
            #temperature=0.5,
            temperature=0.25,
            #max_tokens=1500,
            max_tokens=1000,
            stop=None,
    )
    message = response.choices[0].message.content
    return message


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
    user_message = event.message.text

    # ユーザーがメッセージを送信した直後に表示するメッセージ
    line_bot_api.push_message(user_id, TextSendMessage(text="考えています..."))


    user_messages_with_system_role = create_messages_list(user_id, user_message)

    try:
        gpt3_response = get_gpt3_response(user_messages_with_system_role)
        response_message = {"role": "assistant", "content": gpt3_response}
        add_message_and_truncate(user_id, response_message)
    except openai.error.RateLimitError:
        gpt3_response = "申し訳ありません、現在サーバーが他のリクエストで一杯です。しばらく時間を置いてから再度お試しください。"
        response_message = {"role": "assistant", "content": gpt3_response}
        add_message_and_truncate(user_id, response_message)
    except Exception as e:
        gpt3_response = "申し訳ありません、エラーが発生しました: {}".format(str(e))
        response_message = {"role": "assistant", "content": gpt3_response}
        add_message_and_truncate(user_id, response_message)


    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=gpt3_response)
    )

    response_message = {"role": "assistant", "content": gpt3_response}
    add_message_and_truncate(user_id, response_message)

if __name__ == "__main__":
    app.run()
