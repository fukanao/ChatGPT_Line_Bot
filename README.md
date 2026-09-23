# 20240402 Openai AssistantAPIに対応しました

# ChatGPT_Line_Bot
LINEでChatGPTを使用します。
ubuntuサーバで起動しておきます

.envファイルに各トークンを記述しておきます

    
    pi@raspi3:~/openai/line $ cat .env
    LINE_BOT_API=your_api_token
    LINE_CHANNEL_SECRET_TOKEN=your_channel_token
    OPENAI_API_KEY=your_openai_token




## 画像について質問する

1. LINE のトークに画像を送信します。
2. 「画像を受け取りました」という返信後、「何が写っていますか？」「この文字を翻訳して」などの質問を送ります。
3. 回答後も、同じトークで追加質問できます。

画像と質問は OpenAI Responses API に送信します。画像の入力形式は
[OpenAI の画像入力ドキュメント](https://developers.openai.com/api/docs/guides/images-vision)に準拠しています。
質問前の画像は `chatbot.db` に保存され、複数の Gunicorn ワーカー間で共有されます。
各トークの各ユーザーにつき最新の1枚が対象です。新しい画像を送ると未解析の画像を置き換えます。
画像は解析成功時にローカルの待機データから削除し、API エラー時は再質問できるよう保持します。
質問を送らない場合は次の画像で置き換えるまで保持します。
解析後の会話は既存の `previous_response_id` と `store=True` によって OpenAI 側の履歴を引き継ぎます。

ローカル検証（外部 API 呼び出しなし）:

```bash
myenv/bin/python -m unittest discover -s tests -v
```

変更の反映には、運用中の Bot サービスの再起動が必要です。

## 起動
サービスに登録します
    
    $ cat /etc/systemd/system/line_ai_bot.service
    [Unit]
    Description=LINE AI Bot
    After=network.target
    
    [Service]
    User=pi
    WorkingDirectory=/opt/ChatGPT_Line_Bot
    EnvironmentFile=/opt/ChatGPT_Line_Bot/.env
    ExecStart=/opt/ChatGPT_Line_Bot/myenv/bin/gunicorn -w 2 -b 0.0.0.0:5000 line_bot:app
    Restart=always
    RestartSec=10
    
    [Install]
    WantedBy=multi-user.target


    $ sudo systemctl daemon-reload
    $ sudo systemctl enable remu_line_bot.service
    $ sudo systemctl start remu_line_bot.service
    
    
- ngrok等でLINE側からhttpsでアクセスできるようにしてください

    $ cat /etc/systemd/system/ngrok-line.service
    [Unit]
    Description=ngrok-line Script
    
    [Service]
    ExecStart=/opt/ChatGPT_Line_Bot/myenv/bin/python /opt/ChatGPT_Line_Bot/ngrok-line.py
    User=pi
    Group=pi
    WorkingDirectory=/opt/ChatGPT_Line_Bot/
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
