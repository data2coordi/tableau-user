import csv
import os
import sys
import tableauserverclient as TSC
from dotenv import load_dotenv

# =========================================================
# 1. 初期設定とセーフガード（保護設定）
# =========================================================
# 環境変数 (.env) の読み込み
load_dotenv()
SERVER_URL = os.getenv("TABLEAU_POD_URL")
SITE_NAME = os.getenv("TABLEAU_SITE_NAME", "")
TOKEN_NAME = os.getenv("TABLEAU_PAT_NAME")
TOKEN_SECRET = os.getenv("TABLEAU_PAT_SECRET")

# 保護対象（CSVに載っていなくても削除・脱退させないアカウント・グループ）
SAFEGUARD_USERS = {"h95mori@gmail.com", "data2coordi@gmail.com"}
SAFEGUARD_GROUPS = {"All Users"}
DEFAULT_ROLE = 'Explorer'

# =========================================================
# 2. CSV から「あるべき状態（Expected State）」を取得
# =========================================================
def get_expected_state(csv_path):
    expected_users = set()
    expected_memberships = {} # { "Sales9": {"user1", "user2"} }
    
    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            u = row.get('username', '').strip()
            g = row.get('group', '').strip()
            if u:
                expected_users.add(u)
                if g:
                    if g not in expected_memberships:
                        expected_memberships[g] = set()
                    expected_memberships[g].add(u)
                    
    return expected_users, expected_memberships

# =========================================================
# 3. メイン同期ロジック
# =========================================================
def main(csv_path):
    expected_users, expected_memberships = get_expected_state(csv_path)
    
    # [安全装置] 万が一CSVが空の場合（全消去の事故防止）は停止
    if not expected_users:
        print("[エラー] CSVにユーザーが含まれていません。安全のため処理を停止します。")
        sys.exit(1)

    print("=== [1/4] Tableau Cloud に接続 ===")
    tableau_auth = TSC.PersonalAccessTokenAuth(TOKEN_NAME, TOKEN_SECRET, SITE_NAME)
    server = TSC.Server(SERVER_URL, use_server_version=True)
    
    with server.auth.sign_in(tableau_auth):
        print("=== [2/4] 現在の状態 (Current State) を取得 ===")
        # 現在の全ユーザーと全グループを取得して辞書化
        all_users, _ = server.users.get()
        current_users_map = {u.name: u for u in all_users}
        
        all_groups, _ = server.groups.get()
        current_groups_map = {g.name: g for g in all_groups}
        
        print("\n=== [3/4] ユーザーのアカウント同期 (追加 / 削除) ===")
        # A. 新規ユーザーの作成 (CSVにいて、Tableauにいない)
        for u_name in expected_users:
            if u_name not in current_users_map:
                print(f"[Create User] 新規作成: {u_name}")
                new_user = TSC.UserItem(u_name, DEFAULT_ROLE)
                new_user = server.users.add(new_user)
                current_users_map[u_name] = new_user  # マップを更新
        
        # B. ユーザーの削除 (Tableauにいて、CSVにいない。※保護アカウント除く)
        for u_name, u_item in current_users_map.items():
            if u_name not in expected_users and u_name not in SAFEGUARD_USERS:
                print(f"[Delete User] 削除対象 (退職等): {u_name}")
                server.users.remove(u_item.id)
                
        print("\n=== [4/4] グループと所属の同期 (異動 / 兼務 / 脱退) ===")
        # 【修正点】Tableau上の全グループ ＋ CSVで指定された全グループをループ対象にする
        all_target_group_names = set(current_groups_map.keys()).union(set(expected_memberships.keys()))

        for g_name in all_target_group_names:
            if g_name in SAFEGUARD_GROUPS:
                continue
            
            # このグループに所属すべきユーザーリスト（CSVに記載がない場合は空集合 set()）
            expected_members = expected_memberships.get(g_name, set())
            
            # C. 新規グループの作成 (CSVにのみ存在するグループ)
            if g_name not in current_groups_map:
                print(f"[Create Group] 新規グループ作成: {g_name}")
                new_group = TSC.GroupItem(g_name)
                new_group = server.groups.create(new_group)
                current_groups_map[g_name] = new_group
            
            # グループの現在の所属メンバーを取得
            g_item = current_groups_map[g_name]
            server.groups.populate_users(g_item)
            current_members_map = {u.name: u for u in g_item.users}
            
            # D. グループへの追加配属
            for u_name in expected_members:
                if u_name not in current_members_map:
                    if u_name in current_users_map: # ユーザーが存在する場合のみ
                        print(f"[Add to Group] 追加: {u_name} ➔ {g_name}")
                        server.groups.add_user(g_item, current_users_map[u_name].id)
            
            # E. グループからの脱退 (CSVの該当グループから消えた、またはグループ自体がCSVから消えた場合)
            for u_name, u_item in current_members_map.items():
                if u_name not in expected_members and u_name not in SAFEGUARD_USERS:
                    print(f"[Remove from Group] 脱退: {u_name} ➔ {g_name} から除外")
                    server.groups.remove_user(g_item, u_item.id)
        
        print("\n=== すべての同期処理が正常に完了しました ===")

if __name__ == '__main__':
    csv_file = sys.argv[1] if len(sys.argv) > 1 else 'day1.csv'
    if not os.path.exists(csv_file):
        print(f"[エラー] ファイル {csv_file} が見つかりません。")
        sys.exit(1)
    main(csv_file)