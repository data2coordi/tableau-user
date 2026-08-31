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

# CSVから最初に見つかったグループ名を1つだけ抽出
all_groups = list({g for u in users_data for g in u['groups']})
target_group = all_groups[0] if all_groups else None

print(f"1. テスト対象グループ（1件のみ）: {repr(target_group)}")

if target_group:
    try:
        new_group = server.groups.create(TSC.GroupItem(target_group))
        print(f"2. 作成成功！ Group ID: {new_group.id}, Name: {new_group.name}")
    except Exception as e:
        print(f"2. 作成失敗: {e}")

# 作成後のグループ一覧を再確認
existing_groups = list(TSC.Pager(server.groups))
print(f"3. 作成後のグループ一覧: {[g.name for g in existing_groups]}")

try:
    server.auth.sign_out()
except Exception:
    pass