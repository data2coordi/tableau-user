import os
from dotenv import load_dotenv
import tableauserverclient as TSC

load_dotenv()

tableau_auth = TSC.PersonalAccessTokenAuth(
    os.getenv('TABLEAU_PAT_NAME'),
    os.getenv('TABLEAU_PAT_SECRET'),
    site_id=os.getenv('TABLEAU_SITE_NAME')
)
server = TSC.Server(os.getenv('TABLEAU_POD_URL'), use_server_version=True)
server.auth.sign_in(tableau_auth)

# 1. 現在のログインユーザー情報を取得
user_item = server.users.get_by_id(server.user_id)
print(f"[ログインユーザー] {user_item.name}")
print(f"[ユーザーロール] {user_item.site_role}")

# 2. サーバー上の既存グループ一覧を取得
existing_groups = list(TSC.Pager(server.groups))
print(f"[サーバー上の既存グループ一覧] {[g.name for g in existing_groups]}")

try:
    server.auth.sign_out()
except Exception:
    pass