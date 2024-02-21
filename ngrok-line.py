import os
import subprocess
import time
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("LINE_CHANNEL_TOKEN")

def get_ngrok_url():
    try:
        response = requests.get("http://localhost:4040/api/tunnels")
        data = response.json()
        public_url = data['tunnels'][0]['public_url']
        https_url = public_url.replace("http:", "https:")
        return https_url
    except Exception as e:
        print(f"ngrok URLの取得に失敗しました。エラー: {e}")
        return None


# LINE Webhookを設定
def set_line_webhook(url, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "endpoint": url
    }
    # Webhookのエンドポイントを更新
    response = requests.put("https://api.line.me/v2/bot/channel/webhook/endpoint", headers=headers, json=data)
    return response.status_code


while True:
    # ngrokを起動
    print("ngrokを起動します...")
    ngrok_process = subprocess.Popen(['ngrok', 'http', '5000'])
    
    # URLの取得に少し時間を与える
    time.sleep(5)
    
    # ngrokの公開URLを取得
    url = get_ngrok_url()
    if url:
        print(f"ngrok URLが取得されました: {url}")

        url = get_ngrok_url()
        if url:
            status_code = set_line_webhook(url, TOKEN)
            if status_code == 200:
                print(f"Webhook URLが更新されました: {url}")
            else:
                print("Webhook URLの更新に失敗しました。")
        else:
            print("ngrok URLの取得に失敗しました。")

        # 90分待機 (5400秒)
        time.sleep(5400)
        
        # ngrokを停止
        ngrok_process.terminate()
        print("ngrokを停止しました。90分後に再開します。")
        
        # ショートスリープ（ngrokの終了を待つため）
        time.sleep(5)
    else:
        print("ngrok URLの取得に失敗したため、プロセスを停止します。")
        ngrok_process.terminate()
        
        # エラー発生時には少し待って再試行
        time.sleep(60)
