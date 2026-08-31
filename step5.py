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

# 1. 現在のグループマップを作成
existing_groups = list(TSC.Pager(server.groups))
group_map = {g.name: g for g in existing_groups}

print(f"1. 取得されたグループ数: {len(group_map)}件 ({list(group_map.keys())})\n")

# 2. ユーザー作成とグループ追加
for u in users_data:
    email = u['email']
    role = u['role']
    print(f"--- [ユーザー処理] {email} (Role: {role}) ---")

    # ユーザー追加リクエスト
    user_item = None
    try:
        user_item = server.users.add(TSC.UserItem(name=email, site_role=role))
        print(f"  └ ユーザー作成成功 (ID: {user_item.id})")
    except TSC.ServerResponseError as e:
        if e.code == '409009':
            print(f"  └ ユーザー既存検知: 既存ユーザーオブジェクトを取得します")
            # 既存ユーザー情報を取得
            all_users = list(TSC.Pager(server.users))
            user_item = next((usr for usr in all_users if (usr.email == email or usr.name == email)), None)
        else:
            print(f"  └ ユーザー作成エラー: {e}")
            continue

    # グループ割り当て
    if user_item:
        for g_name in u['groups']:
            group_obj = group_map.get(g_name)
            if group_obj:
                try:
                    server.groups.add_user(group_obj, user_item.id)
                    print(f"  └ [グループ追加成功] {email} -> {g_name}")
                except TSC.ServerResponseError as e:
                    if e.code == '409009':
                        print(f"  └ [グループ追加済み] {email} は既に {g_name} に所属しています")
                    else:
                        print(f"  └ [グループ追加エラー] {g_name}: {e}")
            else:
                print(f"  └ 警告: グループ '{g_name}' がサーバー上に見つかりません")

    time.sleep(0.3)
    print()

try:
    server.auth.sign_out()
    print("処理完了・サインアウト")
except Exception:
    pass