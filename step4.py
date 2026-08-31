import csv
import os
import sys
import time
from dotenv import load_dotenv
import tableauserverclient as TSC

load_dotenv()

# CSVの読み込み
csv_file_path = sys.argv[1] if len(sys.argv) > 1 else 'day20260904.csv'
users_data = []

with open(csv_file_path, mode='r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader, None)
    for row in reader:
        if row and len(row) >= 3:
            email = row[0].strip()
            role = row[1].strip()
            groups = [g.strip() for g in row[2].split(',') if g.strip()]
            users_data.append({'email': email, 'role': role, 'groups': groups})

# ログイン
site_name = os.getenv('TABLEAU_SITE_NAME')
tableau_auth = TSC.PersonalAccessTokenAuth(
    os.getenv('TABLEAU_PAT_NAME'),
    os.getenv('TABLEAU_PAT_SECRET'),
    site_id=site_name
)
server = TSC.Server(os.getenv('TABLEAU_POD_URL'), use_server_version=True)
server.auth.sign_in(tableau_auth)

all_groups = {g for u in users_data for g in u['groups']}
print(f"1. 作成対象グループ一覧: {all_groups}\n")

# 1つずつグループを作成し、直後に存在を確認する
for g_name in all_groups:
    print(f"--- [{g_name}] の処理を開始 ---")
    
    # 1. 作成リクエスト送信
    try:
        server.groups.create(TSC.GroupItem(g_name))
        print(f"  └ POSTリクエスト成功")
    except TSC.ServerResponseError as e:
        if e.code == '409009':
            print(f"  └ POSTリクエストで409009検知（サーバー側作成完了）")
        else:
            print(f"  └ 予期せぬエラー: {e}")

    # サーバー側の反映待ち（0.5秒ウェイト）
    time.sleep(0.5)

    # 2. 実際に作成されたか一覧を取得して個別確認
    try:
        current_groups = list(TSC.Pager(server.groups))
        group_names = [g.name for g in current_groups]
        if g_name in group_names:
            print(f"  └ サーバー存在確認: OK (現在の全グループ: {group_names})")
        else:
            print(f"  └ サーバー存在確認: NG (見つかりません)")
    except Exception as check_err:
        print(f"  └ 確認用GETリクエスト失敗: {check_err}")

    print()

try:
    server.auth.sign_out()
except Exception:
    pass