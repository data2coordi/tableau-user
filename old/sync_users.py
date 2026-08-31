import csv
import os
import sys
from dotenv import load_dotenv
import tableauserverclient as TSC

load_dotenv()

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

tableau_auth = TSC.PersonalAccessTokenAuth(
    os.getenv('TABLEAU_PAT_NAME'),
    os.getenv('TABLEAU_PAT_SECRET'),
    site_id=os.getenv('TABLEAU_SITE_NAME')
)

server = TSC.Server(os.getenv('TABLEAU_POD_URL'))
# 明示的にバージョンを指定 (例: 3.19 や 3.20 など安定版)
server.version = '3.19'

server.auth.sign_in(tableau_auth)

# 対象グループの一覧
all_groups = {g for u in users_data for g in u['groups']}
print(f"[作成対象グループ一覧] {all_groups}")

for g_name in all_groups:
    print(f"[作成対象グループ] {g_name}")
    try:
        group_item = server.groups.create(TSC.GroupItem(g_name))
        print(f"[グループ作成成功] {g_name}")
    except TSC.ServerResponseError as e:
        print(f"[APIエラー詳細] Code: {e.code}, Summary: {e.summary}, Detail: {e.detail}")

try:
    server.auth.sign_out()
except Exception:
    pass