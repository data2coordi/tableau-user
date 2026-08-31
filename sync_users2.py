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
    next(reader, None)  # ヘッダー行をスキップ
    for row in reader:
        if row and len(row) >= 3:
            email = row[0].strip()
            role = row[1].strip()
            groups = [g.strip() for g in row[2].split(',') if g.strip()]
            users_data.append({'email': email, 'role': role, 'groups': groups})

# 1. 接続とログイン
site_name = os.getenv('TABLEAU_SITE_NAME')
print(f"[1. 接続開始] Site Name: {site_name}")

tableau_auth = TSC.PersonalAccessTokenAuth(
    os.getenv('TABLEAU_PAT_NAME'),
    os.getenv('TABLEAU_PAT_SECRET'),
    site_id=site_name
)
server = TSC.Server(os.getenv('TABLEAU_POD_URL'), use_server_version=True)
server.auth.sign_in(tableau_auth)
print("[1. ログイン成功]")

# 2. サーバー上の全グループを事前一括取得 (GET)
print("\n[2. サーバー上の既存グループ一覧を取得中...]")
existing_groups = list(TSC.Pager(server.groups))
group_map = {g.name: g for g in existing_groups}
print(f"  └ 取得完了 ({len(group_map)}件): {list(group_map.keys())}")

# 3. 未作成のグループのみ判定して作成 (POST) + インターバル
csv_groups = {g for u in users_data for g in u['groups']}
print(f"\n[3. グループ作成判定] CSV内の対象グループ: {csv_groups}")

for g_name in csv_groups:
    if g_name in group_map:
        print(f"  └ [スキップ] グループ '{g_name}' は既に存在します")
    else:
        print(f"  └ [新規作成実行] グループ '{g_name}' を作成します...")
        new_group = server.groups.create(TSC.GroupItem(g_name))
        group_map[g_name] = new_group
        print(f"  └ [作成成功] グループ '{g_name}' (ID: {new_group.id})")
        
        # 連続リクエストによるキャッシュ不整合防止のためのインターバル
        time.sleep(1)

# 4. サーバー上の全ユーザーを事前一括取得 (GET)
print("\n[4. サーバー上の既存ユーザー一覧を取得中...]")
existing_users = list(TSC.Pager(server.users))
user_map = {u.email if u.email else u.name: u for u in existing_users}
print(f"  └ 取得完了 ({len(user_map)}件): {list(user_map.keys())}")

# 5. 未作成のユーザーのみ作成し、未所属の場合のみグループに追加 + インターバル
print("\n[5. ユーザー作成およびグループ割り当て判定]")
for u in users_data:
    email = u['email']
    role = u['role']
    print(f"\n--- ユーザー処理: {email} ({role}) ---")

    # ユーザーの存在判定と作成
    if email in user_map:
        user_item = user_map[email]
        print(f"  └ [スキップ] ユーザー '{email}' は既に存在します")
    else:
        print(f"  └ [新規作成実行] ユーザー '{email}' を作成します...")
        user_item = server.users.add(TSC.UserItem(name=email, site_role=role))
        user_map[email] = user_item
        print(f"  └ [作成成功] ユーザー '{email}' (ID: {user_item.id})")
        time.sleep(1)

    # グループ割り当ての判定
    for g_name in u['groups']:
        group_obj = group_map.get(g_name)
        if group_obj:
            # 対象グループの既存メンバーを事前に取得
            group_members = [usr.name for usr in TSC.Pager(server.groups.populate_users, group_obj)]
            if email in group_members:
                print(f"  └ [スキップ] {email} は既にグループ '{g_name}' に所属しています")
            else:
                print(f"  └ [グループ追加実行] {email} -> {g_name}...")
                server.groups.add_user(group_obj, user_item.id)
                print(f"  └ [追加成功] {email} -> {g_name}")
                time.sleep(1)

try:
    server.auth.sign_out()
    print("\n[6. サインアウト完了]")
except Exception:
    pass