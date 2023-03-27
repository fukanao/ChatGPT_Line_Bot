# ChatGPT_Line_Bot
LINEでChatGPTのレムと会話するときにubuntuサーバで起動しておきます

.envファイルに各トークンを記述しておきます

    
    pi@raspi3:~/openai/line $ cat .env
    LINE_BOT_API=your_api_token
    HANDLER=your_channel_token
    OPENAI_API_KEY=your_openai_token




## 起動
サービスに登録します
    pi@raspi3:~/openai/line $ cat /etc/systemd/system/remu_line_bot.service
    [Unit]
    Description=Remu LINE Bot
    After=network.target
    
    [Service]
    User=pi
    WorkingDirectory=/home/pi/openai/line
    EnvironmentFile=/home/pi/openai/line/.env
    ExecStart=/usr/bin/python3 /home/pi/openai/line/Remu_line_bot.py
    Restart=always
    RestartSec=10
    
    [Install]
    WantedBy=multi-user.target


    $ sudo systemctl daemon-reload
    $ sudo systemctl enable remu_line_bot.service
    $ sudo systemctl start remu_line_bot.service
    
    
- ngrok等でLINE側からhttpsでアクセスできるようにしてください
