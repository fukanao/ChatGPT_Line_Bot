from openai import OpenAI
import os
from dotenv import load_dotenv

# OpenAIのAPIキーをセットアップします。
load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)
# ファイル名を指定します
filename = "user_thread_pairs.txt"

# ファイルを読み込み、各行を処理します。
try:
    with open(filename, "r") as file:
        lines = file.readlines()

    for line in lines:
        # ユーザIDとスレッド名を分離します。
        user_id, thread_id = line.strip().split(",")

        try:
            # スレッドを削除します。
            response = client.beta.threads.delete(thread_id)

            # 削除が成功したことを確認します。
            print(f"スレッド {thread_id} の削除に成功しました: {response}")

        except Exception as e:
            print(f"スレッド {thread_id} の削除に失敗しました: {str(e)}")

    # 全てのスレッドを削除した後、ファイルを空にします。
    with open(filename, "w") as file:
        file.write("")

    print(f"{filename} ファイルを空にしました。")

except FileNotFoundError:
    print(f"ファイル {filename} が見つかりませんでした。")

except Exception as e:
    print(f"エラーが発生しました: {str(e)}")
