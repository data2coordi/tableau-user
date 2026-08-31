import csv
import os
import sys
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
print(f"1. 作成対象グループ一覧: {all_groups}")

# グループ作成（409009 エラーは作成成功と同等として扱う）
for g_name in all_groups:
    try:
        server.groups.create(TSC.GroupItem(g_name))
        print(f"  └ [作成成功] {g_name}")
    except TSC.ServerResponseError as e:
        if e.code == '409009':
            print(f"  └ [作成完了/既存検知] {g_name} (409009レスポンス)")
        else:
            raise e

# 最終確認: サーバー上のグループ一覧を取得
existing_groups = list(TSC.Pager(server.groups))
print(f"\n2. 最終結果 - サーバー上のグループ一覧 ({len(existing_groups)}件):")
for g in existing_groups:
    print(f"   - {g.name} (ID: {g.id})")

try:
    server.auth.sign_out()
except Exception:
    pass