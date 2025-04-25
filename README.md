# 20240402 Openai AssistantAPIに対応しました

# ChatGPT_Line_Bot
LINEでChatGPTを使用します。
ubuntuサーバで起動しておきます

.envファイルに各トークンを記述しておきます

    
    pi@raspi3:~/openai/line $ cat .env
    LINE_BOT_API=your_api_token
    LINE_CHANNEL_SECRET_TOKEN=your_channel_token
    OPENAI_KEY=your_openai_token




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
