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

def load_csv(file_path):
    users = {}
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            users[row['username']] = {
                'site_role': row['site_role'],
                'group': row['group']
            }
    return users

def sync_tableau(csv_file):
    print(f"--- Starting Sync with {csv_file} ---")
    target_users = load_csv(csv_file)

    tableau_auth = TSC.PersonalAccessTokenAuth(
        token_name=TABLEAU_PAT_NAME,
        personal_access_token=TABLEAU_PAT_SECRET,
        site_id=TABLEAU_SITE_NAME
    )
    
    server = TSC.Server(TABLEAU_POD_URL, use_server_version=True)

    with server.auth.sign_in(tableau_auth):
        print("[Auth] Signed in successfully.")
        
        req_options = TSC.RequestOptions(pagesize=1000)
        existing_users = {u.name: u for u in TSC.Pager(server.users, req_options)}
        existing_groups = {g.name: g for g in TSC.Pager(server.groups, req_options)}

        # 1. グループの作成
        csv_groups = set(details['group'] for details in target_users.values())
        for grp_name in csv_groups:
            matched_group = next((g for g in existing_groups.values() if g.name.lower() == grp_name.lower()), None)
            
            if not matched_group:
                try:
                    new_grp = TSC.GroupItem(grp_name)
                    created_grp = server.groups.create(new_grp)
                    existing_groups[created_grp.name] = created_grp
                    print(f"[Group] Created new group: {created_grp.name}")
                except TSC.ServerResponseError as e:
                    if "409009" in str(e): 
                        print(f"[Group] Group '{grp_name}' already exists. Refreshing lists...")
                        existing_groups = {g.name: g for g in TSC.Pager(server.groups, req_options)}
                    else:
                        print(f"[Group Error] Failed to create {grp_name}: {e}")

        admin_roles = ["SiteAdministratorExplorer", "SiteAdministratorCreator", "SiteAdministrator", "ServerAdministrator"]

        # 2 & 3. ユーザーの追加・更新とグループ同期
        for email, details in target_users.items():
            role = details['site_role']
            target_group_name = details['group']

            if email not in existing_users:
                new_user = TSC.UserItem(email, role)
                try:
                    added_user = server.users.add(new_user)
                    existing_users[email] = added_user
                    print(f"[User Added] {email} (Role: {role})")
                except TSC.ServerResponseError as e:
                    print(f"[User Error] Failed to add {email}: {e}")
                    continue
            
            curr_user = existing_users.get(email)
            if not curr_user:
                continue

            if curr_user.site_role not in admin_roles and curr_user.site_role != role:
                try:
                    curr_user.site_role = role
                    updated_user = server.users.update(curr_user)
                    existing_users[email] = updated_user
                    print(f"[User Updated] {email} -> {role}")
                except TSC.ServerResponseError as e:
                    print(f"[User Error] Failed to update role for {email}: {e}")

            # --- グループ異動（Sync）処理 ---
            server.users.populate_groups(curr_user)
            current_user_groups = {}
            
            try:
                # ※ TSCライブラリのバグ(400006)を回避するため、内包表記ではなくforループで個別に回し例外をキャッチ
                for g in curr_user.groups:
                    current_user_groups[g.name] = g
            except TSC.ServerResponseError as e:
                # 1ページ目(最大100件)は既に格納できているため、ページネーションのバグは無視する
                if "400006" not in str(e):
                    print(f"  [Group Fetch Error] Failed to fetch groups for {email}: {e}")

            target_group_obj = next((g for g in existing_groups.values() if g.name.lower() == target_group_name.lower()), None)

            # 古いグループからの削除
            for cg_name, cg_item in current_user_groups.items():
                if cg_name == "All Users": 
                    continue 
                
                if not target_group_obj or cg_item.id != target_group_obj.id:
                    try:
                        server.groups.remove_user(cg_item, curr_user.id)
                        print(f"  [Group Sync] Removed {email} from old group '{cg_name}'")
                    except TSC.ServerResponseError as e:
                        print(f"  [Group Error] Failed to remove {email} from '{cg_name}': {e}")

            # 新しいグループへの追加
            if target_group_obj and target_group_obj.name not in current_user_groups:
                try:
                    server.groups.add_user(target_group_obj, curr_user.id)
                    print(f"  [Group Sync] Added {email} to target group '{target_group_obj.name}'")
                except TSC.ServerResponseError as e:
                    if "409011" not in str(e):
                        print(f"  [Group Error] Failed to add {email} to '{target_group_obj.name}': {e}")

        # 4. CSVに存在しないユーザーの処理 (Unlicense化)
        for email, user_obj in existing_users.items():
            if email not in target_users:
                if user_obj.site_role not in admin_roles and user_obj.site_role != "Unlicensed":
                    user_obj.site_role = "Unlicensed"
                    try:
                        server.users.update(user_obj)
                        print(f"[User Removed] Unlicensed (removed from AD): {email}")
                    except TSC.ServerResponseError as e:
                        print(f"[User Error] Failed to unlicense {email}: {e}")

    print(f"--- Sync Complete for {csv_file} ---\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 sync_users.py <csv_file>")
        sys.exit(1)
    
    csv_filename = sys.argv[1]
    if not os.path.exists(csv_filename):
        print(f"Error: File '{csv_filename}' not found.")
        sys.exit(1)
        
    sync_tableau(csv_filename)
