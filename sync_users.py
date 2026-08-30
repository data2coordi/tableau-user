import sys
import os
import csv
from dotenv import load_dotenv
import tableauserverclient as TSC

load_dotenv()

TABLEAU_POD_URL = os.getenv("TABLEAU_POD_URL")
TABLEAU_SITE_NAME = os.getenv("TABLEAU_SITE_NAME")
TABLEAU_PAT_NAME = os.getenv("TABLEAU_PAT_NAME")
TABLEAU_PAT_SECRET = os.getenv("TABLEAU_PAT_SECRET")

ADMIN_ROLES = ["SiteAdministratorExplorer", "SiteAdministratorCreator", "SiteAdministrator", "ServerAdministrator"]


def load_csv_data(file_path):
    """1. CSVを読み込み、ユーザーごとの情報を辞書化"""
    users_data = {}
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_group_str = row.get('group', '')
            group_list = [g.strip() for g in raw_group_str.split(',') if g.strip()]
            users_data[row['username']] = {
                'site_role': row['site_role'],
                'groups': group_list
            }
    return users_data


def ensure_groups_exist(server, csv_groups, existing_groups):
    """2. CSVに存在するグループがTableauになければ自動作成"""
    for grp_name in csv_groups:
        if not any(g.lower() == grp_name.lower() for g in existing_groups.keys()):
            try:
                created_g = server.groups.create(TSC.GroupItem(grp_name))
                existing_groups[created_g.name] = created_g
                print(f"[Group] 作成完了: {created_g.name}")
            except Exception:
                pass  # 既にある等のエラーは安全に無視


def sync_user_groups(server, curr_user, target_groups, existing_groups):
    """3. 特定ユーザーのグループ所属（参加・離脱）を同期"""
    try:
        server.users.populate_groups(curr_user)
        curr_group_names = [g.name for g in curr_user.groups]
    except Exception:
        curr_group_names = []

    # ① 対象グループへの追加
    for tg_name in target_groups:
        if not any(tg_name.lower() == cg.lower() for cg in curr_group_names):
            g_obj = next((g for name, g in existing_groups.items() if name.lower() == tg_name.lower()), None)
            if g_obj:
                try:
                    server.groups.add_user(g_obj, curr_user.id)
                    print(f"  [Group Sync] '{g_obj.name}' に {curr_user.name} を追加")
                except Exception:
                    pass

    # ② 不要なグループからの離脱 (All Usersは除く)
    for cg_name in curr_group_names:
        if cg_name != "All Users" and not any(cg_name.lower() == tg.lower() for tg in target_groups):
            g_obj = existing_groups.get(cg_name)
            if g_obj:
                try:
                    server.groups.remove_user(g_obj, curr_user.id)
                    print(f"  [Group Sync] '{cg_name}' から {curr_user.name} を外しました")
                except Exception:
                    pass


def main_sync(csv_file):
    """メイン同期実行プロセス"""
    print(f"--- 同期開始: {csv_file} ---")
    csv_users_data = load_csv_data(csv_file)

    auth = TSC.PersonalAccessTokenAuth(TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET, site_id=TABLEAU_SITE_NAME)
    server = TSC.Server(TABLEAU_POD_URL, use_server_version=True)

    with server.auth.sign_in(auth):
        print("[Auth] Tableauサーバーにログインしました。")
        req_options = TSC.RequestOptions(pagesize=1000)

        # 1. 不足しているグループの作成とリスト最新化
        existing_groups = {g.name: g for g in TSC.Pager(server.groups, req_options)}
        all_csv_groups = {grp for details in csv_users_data.values() for grp in details['groups']}
        ensure_groups_exist(server, all_csv_groups, existing_groups)
        
        # グループ一覧を最新化
        existing_groups = {g.name: g for g in TSC.Pager(server.groups, req_options)}

        # 2. ユーザーの追加・更新・グループ同期
        existing_users = {u.name: u for u in TSC.Pager(server.users, req_options)}

        for email, details in csv_users_data.items():
            role = details['site_role']
            target_groups = details['groups']

            # ユーザー追加
            if email not in existing_users:
                try:
                    existing_users[email] = server.users.add(TSC.UserItem(email, role))
                    print(f"[User Added] 追加完了: {email} ({role})")
                except Exception:
                    # ID連携エラー対策：作成自体は成功している場合があるため一覧再取得
                    existing_users = {u.name: u for u in TSC.Pager(server.users, req_options)}

            curr_user = existing_users.get(email)
            if not curr_user:
                continue

            # ロール更新 (管理者は保護)
            if curr_user.site_role not in ADMIN_ROLES and curr_user.site_role != role:
                try:
                    curr_user.site_role = role
                    existing_users[email] = server.users.update(curr_user)
                    print(f"[User Updated] ロール変更: {email} -> {role}")
                except Exception as e:
                    print(f"[User Error] ロール変更失敗 {email}: {e}")

            # グループ同期関数を呼び出し
            sync_user_groups(server, curr_user, target_groups, existing_groups)

        # 3. CSVに存在しないユーザーの無効化 (Unlicensed)
        for email, user_obj in existing_users.items():
            if email not in csv_users_data and user_obj.site_role not in ADMIN_ROLES and user_obj.site_role != "Unlicensed":
                try:
                    user_obj.site_role = "Unlicensed"
                    server.users.update(user_obj)
                    print(f"[User Removed] Unlicensedに変更: {email}")
                except Exception as e:
                    print(f"[User Error] 無効化失敗 {email}: {e}")

    print(f"--- 同期完了: {csv_file} ---\n")


if __name__ == "__main__":
    if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
        print("使い方: python3 sync_users.py <csvファイル名>")
        sys.exit(1)
    main_sync(sys.argv[1])