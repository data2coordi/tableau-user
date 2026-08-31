import sys
import os
from dotenv import load_dotenv
import tableauserverclient as TSC

load_dotenv()

TABLEAU_POD_URL = os.getenv("TABLEAU_POD_URL")
TABLEAU_SITE_NAME = os.getenv("TABLEAU_SITE_NAME")
TABLEAU_PAT_NAME = os.getenv("TABLEAU_PAT_NAME")
TABLEAU_PAT_SECRET = os.getenv("TABLEAU_PAT_SECRET")

ADMIN_ROLES = ["SiteAdministratorExplorer", "SiteAdministratorCreator", "SiteAdministrator", "ServerAdministrator"]


def cleanup_tableau():
    print("--- クリーンアップ処理を開始します ---")

    auth = TSC.PersonalAccessTokenAuth(
        token_name=TABLEAU_PAT_NAME,
        personal_access_token=TABLEAU_PAT_SECRET,
        site_id=TABLEAU_SITE_NAME
    )
    server = TSC.Server(TABLEAU_POD_URL, use_server_version=True)

    # with文を使わずに直接サインイン
    server.auth.sign_in(auth)
    print("[Auth] Tableauサーバーにログインしました。")

    try:
        req_options = TSC.RequestOptions(pagesize=1000)

        # 1. グループの削除
        print("\n--- 1. グループの削除 ---")
        all_groups = list(TSC.Pager(server.groups, req_options))
        for group in all_groups:
            if group.name != "All Users":
                try:
                    server.groups.delete(group.id)
                    print(f"[Group Deleted] 削除完了: {group.name}")
                except TSC.ServerResponseError as e:
                    if "404012" in str(e):
                        print(f"[Group Deleted] 削除完了 (参照ID更新済み): {group.name}")
                    else:
                        print(f"[Group Error] 削除失敗 {group.name}: {e}")
            else:
                print(f"[Group Skipped] システムグループのためスキップ: {group.name}")

        # 2. ユーザーの削除
        print("\n--- 2. ユーザーの削除 ---")
        all_users = list(TSC.Pager(server.users, req_options))
        for user in all_users:
            if user.site_role not in ADMIN_ROLES:
                try:
                    server.users.remove(user.id)
                    print(f"[User Deleted] 削除完了: {user.name}")
                except TSC.ServerResponseError as e:
                    if "400046" in str(e) or "Failed to sync link user" in str(e):
                        print(f"[User Deleted] 削除完了 (内部ID同期通知のみスキップ): {user.name}")
                    else:
                        print(f"[User Error] 削除失敗 {user.name}: {e}")
            else:
                print(f"[User Skipped] 管理者のためスキップ: {user.name}")

    finally:
        # 明示的にサインアウトを実行し、セッション無効化時の例外を安全に捕獲して無視する
        try:
            server.auth.sign_out()
        except Exception:
            pass  # 既にセッションが切れている場合は何もしない

    print("\n--- クリーンアップ完了 ---")


if __name__ == "__main__":
    #confirm = input("管理者以外のユーザーとカスタムグループを【すべて削除】します。実行しますか？ (y/N): ")
    #if confirm.lower() == 'y':
    cleanup_tableau()