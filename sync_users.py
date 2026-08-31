import sys
import os
import csv
import time
from dotenv import load_dotenv
import tableauserverclient as TSC

load_dotenv()

TABLEAU_POD_URL = os.getenv("TABLEAU_POD_URL")
TABLEAU_SITE_NAME = os.getenv("TABLEAU_SITE_NAME")
TABLEAU_PAT_NAME = os.getenv("TABLEAU_PAT_NAME")
TABLEAU_PAT_SECRET = os.getenv("TABLEAU_PAT_SECRET")

ADMIN_ROLES = ["SiteAdministratorExplorer", "SiteAdministratorCreator", "SiteAdministrator", "ServerAdministrator"]
DEFAULT_AUTH_SETTING = "TableauIDWithMFA"


def load_csv_data(file_path):
    users_data = {}
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_group_str = row.get('group', '')
            group_list = [g.strip() for g in raw_group_str.split(',') if g.strip()]
            users_data[row['username'].strip().lower()] = {
                'site_role': row['site_role'],
                'groups': group_list
            }
    return users_data


def ensure_groups_exist(server, csv_groups, existing_groups):
    """CSVに存在するグループが存在しない場合のみ作成"""
    for grp_name in csv_groups:
        if grp_name.lower() == "all users":
            continue
            
        if not any(g.lower() == grp_name.lower() for g in existing_groups.keys()):
            try:
                created_g = server.groups.create(TSC.GroupItem(grp_name))
                existing_groups[created_g.name] = created_g
                print(f"[Group] 作成完了: {created_g.name}")
            except Exception:
                print(f"[Group Skip] '{grp_name}' の作成をスキップ（既存または処理中）")


def main_sync(csv_file):
    print(f"--- 同期開始: {csv_file} ---")
    csv_users_data = load_csv_data(csv_file)

    auth = TSC.PersonalAccessTokenAuth(TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET, site_id=TABLEAU_SITE_NAME)
    server = TSC.Server(TABLEAU_POD_URL, use_server_version=True)

    server.auth.sign_in(auth)
    print("[Auth] Tableauサーバーにログインしました。")

    try:
        req_options = TSC.RequestOptions(pagesize=1000)

        # 1. グループ一覧の取得・作成
        raw_groups = list(TSC.Pager(server.groups, req_options))
        existing_groups = {g.name: g for g in raw_groups}
        all_csv_groups = {grp for details in csv_users_data.values() for grp in details['groups']}
        ensure_groups_exist(server, all_csv_groups, existing_groups)
        
        # 最新のグループ一覧を取得（All Users除く）
        group_map_by_name = {
            g.name.lower(): g for g in TSC.Pager(server.groups, req_options) if g.name != "All Users"
        }
        group_map_by_id = {g.id: g for g in group_map_by_name.values()}

        # 2. 全ユーザーの取得
        existing_users = {u.name.lower(): u for u in TSC.Pager(server.users, req_options)}

        # 3. ユーザー作成・更新およびグループ同期
        for email, details in csv_users_data.items():
            role = details['site_role']
            target_group_names = {g.lower() for g in details['groups']}

            curr_user = existing_users.get(email)
            is_new_user = False

            # --- ユーザー追加 ---
            if not curr_user:
                try:
                    new_user = TSC.UserItem(email, role, auth_setting=DEFAULT_AUTH_SETTING)
                    added_user = server.users.add(new_user)
                    
                    # サーバー側の非同期反映を待つため1.5秒待機
                    time.sleep(1.5)
                    
                    curr_user = server.users.get_by_id(added_user.id)
                    existing_users[email] = curr_user
                    is_new_user = True
                    print(f"[User Added] 追加完了: {email} ({role})")
                except Exception as e:
                    print(f"[User Error] 追加失敗 {email}: {e}")
                    continue
            else:
                # ロール更新
                if curr_user.site_role not in ADMIN_ROLES and curr_user.site_role != role:
                    try:
                        curr_user.site_role = role
                        curr_user = server.users.update(curr_user)
                        print(f"[User Updated] ロール変更: {email} -> {role}")
                    except Exception as e:
                        print(f"[User Error] ロール変更失敗 {email}: {e}")

            if not curr_user:
                continue

            # --- 所属グループの同期 ---
            try:
                server.users.populate_groups(curr_user)
                current_group_ids = {g.id for g in curr_user.groups if g.name != "All Users"}
            except Exception:
                current_group_ids = set()

            # 所属すべきグループIDのセット
            target_group_ids = {
                group_map_by_name[g_name].id
                for g_name in target_group_names
                if g_name in group_map_by_name
            }

            # 追加が必要なグループのみ処理
            to_add_ids = target_group_ids - current_group_ids
            for g_id in to_add_ids:
                g_obj = group_map_by_id.get(g_id)
                if not g_obj:
                    continue
                try:
                    server.groups.add_user(g_obj, curr_user.id)
                    print(f"  [Group Sync] '{g_obj.name}' に {curr_user.name} を追加")
                except TSC.ServerResponseError as e:
                    if "409011" in str(e):
                        print(f"  [Group Skip] '{g_obj.name}' には既に所属しています")
                    else:
                        print(f"  [Group Error] 追加失敗 '{g_obj.name}': {e}")
                except Exception as e:
                    print(f"  [Group Error] 追加失敗 '{g_obj.name}': {e}")

            # 削除が必要なグループのみ処理
            to_remove_ids = current_group_ids - target_group_ids
            for g_id in to_remove_ids:
                g_obj = group_map_by_id.get(g_id)
                if g_obj:
                    try:
                        server.groups.remove_user(g_obj, curr_user.id)
                        print(f"  [Group Sync] '{g_obj.name}' から {curr_user.name} を削除")
                    except Exception as e:
                        print(f"  [Group Error] 削除失敗 '{g_obj.name}': {e}")

        # 4. CSVに存在しないユーザーの無効化
        for email, user_obj in existing_users.items():
            if email not in csv_users_data and user_obj.site_role not in ADMIN_ROLES and user_obj.site_role != "Unlicensed":
                try:
                    user_obj.site_role = "Unlicensed"
                    server.users.update(user_obj)
                    print(f"[User Removed] Unlicensedに変更: {email}")
                except Exception as e:
                    pass

    finally:
        try:
            server.auth.sign_out()
        except Exception:
            pass

    print(f"--- 同期完了: {csv_file} ---\n")

if __name__ == "__main__":
    if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
        print("使い方: python3 sync_users.py <csvファイル名>")
        sys.exit(1)
    main_sync(sys.argv[1])