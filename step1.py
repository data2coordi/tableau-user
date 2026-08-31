import os
from dotenv import load_dotenv
import tableauserverclient as TSC

load_dotenv()

site_name = os.getenv('TABLEAU_SITE_NAME')
print(f"1. 接続先 SITE_NAME: {site_name}")

tableau_auth = TSC.PersonalAccessTokenAuth(
    os.getenv('TABLEAU_PAT_NAME'),
    os.getenv('TABLEAU_PAT_SECRET'),
    site_id=site_name
)
server = TSC.Server(os.getenv('TABLEAU_POD_URL'), use_server_version=True)

print("2. ログイン実行中...")
server.auth.sign_in(tableau_auth)
print(f"3. ログイン成功 (Site ID: {server.site_id})")

# 既存グループの取得
existing_groups = list(TSC.Pager(server.groups))
group_names = [g.name for g in existing_groups]

print(f"4. 取得された既存グループ一覧 ({len(group_names)}件): {group_names}")

try:
    server.auth.sign_out()
    print("5. サインアウト完了")
except Exception:
    pass