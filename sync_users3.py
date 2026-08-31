import csv
import os
import sys
import tableauserverclient as TSC
from dotenv import load_dotenv

# =========================================================
# 1. 初期設定とセーフガード（保護設定）
# =========================================================
load_dotenv()
SERVER_URL = os.getenv("TABLEAU_POD_URL")
SITE_NAME = os.getenv("TABLEAU_SITE_NAME", "")
TOKEN_NAME = os.getenv("TABLEAU_PAT_NAME")
TOKEN_SECRET = os.getenv("TABLEAU_PAT_SECRET")

# 保護対象（CSVになくても削除・脱退させないアカウント・グループ）
SAFEGUARD_USERS = {"h95mori@gmail.com", "data2coordi@gmail.com"}
SAFEGUARD_GROUPS = {"All Users"}
DEFAULT_ROLE = 'Explorer'


# =========================================================
# 2. CSV から「あるべき状態（CSV State）」を取得
# =========================================================
def get_csv_state(csv_path):
    csv_users = set()
    csv_group_members = {}  # 例: { "Sales9": {"user1", "user2"} }

    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            username = row.get('username', '').strip()
            group_name = row.get('group', '').strip()

            if username:
                csv_users.add(username)
                if group_name:
                    if group_name not in csv_group_members:
                        csv_group_members[group_name] = set()
                    csv_group_members[group_name].add(username)

    return csv_users, csv_group_members


# =========================================================
# 3. メイン同期ロジック
# =========================================================
def main(csv_path):
    # CSV（あるべき姿）の情報を取得
    csv_users, csv_group_members = get_csv_state(csv_path)

    # [安全装置] 万が一CSVが空の場合（全消去の事故防止）は停止
    if not csv_users:
        print("[エラー] CSVにユーザーが含まれていません。安全のため処理を停止します。")
        sys.exit(1)

    print("=== [1/4] Tableau Cloud に接続 ===")
    tableau_auth = TSC.PersonalAccessTokenAuth(TOKEN_NAME, TOKEN_SECRET, SITE_NAME)
    server = TSC.Server(SERVER_URL, use_server_version=True)

    with server.auth.sign_in(tableau_auth):
        print("=== [2/4] Server上の現在の状態 (Server State) を取得 ===")
        # Server上の全ユーザー・全グループを取得して辞書化
        raw_server_users, _ = server.users.get()
        server_users_map = {u.name: u for u in raw_server_users}

        raw_server_groups, _ = server.groups.get()
        server_groups_map = {g.name: g for g in raw_server_groups}

        print("\n=== [3/4] ユーザーのアカウント同期 (追加 / 削除) ===")
        # A. 新規ユーザーの作成 (CSVにいて、Tableau Serverにいない)
        for username in csv_users:
            if username not in server_users_map:
                print(f"[Create User] 新規作成: {username}")
                new_user = TSC.UserItem(username, DEFAULT_ROLE)
                created_user = server.users.add(new_user)
                server_users_map[username] = created_user  # 辞書を最新化

        # B. ユーザーの削除 (Tableau Serverにいて、CSVにいない。※保護アカウント除く)
        for username, user_item in server_users_map.items():
            if username not in csv_users and username not in SAFEGUARD_USERS:
                print(f"[Delete User] 削除対象 (退職等): {username}")
                server.users.remove(user_item.id)

        print("\n=== [4/4] グループと所属の同期 (異動 / 兼務 / 脱退) ===")
        # Tableau上の全グループ ＋ CSVで指定された全グループをループ対象にする
        target_group_names = set(server_groups_map.keys()).union(set(csv_group_members.keys()))

        for group_name in target_group_names:
            if group_name in SAFEGUARD_GROUPS:
                continue


            # C. 新規グループの作成 (CSVにのみ存在するグループ)
            if group_name not in server_groups_map:
                print(f"[Create Group] 新規グループ作成: {group_name}")
                new_group = TSC.GroupItem(group_name)
                created_group = server.groups.create(new_group)
                server_groups_map[group_name] = created_group

            # 対象グループの現在の所属メンバーをサーバーから取得
            group_item = server_groups_map[group_name]
            server.groups.populate_users(group_item)
            server_members_map = {u.name: u for u in group_item.users}

            # D. グループへの追加配属(対象グループにCSVで所属しているがサーバー側では所属していない)
            # このグループにあるべきメンバーリスト（CSVに記載がない場合は空集合）
            expected_members = csv_group_members.get(group_name, set())
            
            for username in expected_members:
                if username not in server_members_map:
                    if username in server_users_map:  # ユーザーがTableau上に存在する場合のみ
                        print(f"[Add to Group] 追加: {username} ➔ {group_name}")
                        server.groups.add_user(group_item, server_users_map[username].id)

            # E. グループからの脱退 (CSVの該当グループから消えた)
            for username, user_item in server_members_map.items():
                if username not in expected_members and username not in SAFEGUARD_USERS:
                    print(f"[Remove from Group] 脱退: {username} ➔ {group_name} から除外")
                    server.groups.remove_user(group_item, user_item.id)

        print("\n=== すべての同期処理が正常に完了しました ===")


if __name__ == '__main__':
    csv_file = sys.argv[1] if len(sys.argv) > 1 else 'day1.csv'
    if not os.path.exists(csv_file):
        print(f"[エラー] ファイル {csv_file} が見つかりません。")
        sys.exit(1)
    main(csv_file)