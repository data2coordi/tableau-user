import sys
import os
import csv
from dotenv import load_dotenv
import tableauserverclient as TSC

# .envファイルから環境変数を読み込む
load_dotenv()

TABLEAU_POD_URL = os.getenv("TABLEAU_POD_URL")
TABLEAU_SITE_NAME = os.getenv("TABLEAU_SITE_NAME")
TABLEAU_PAT_NAME = os.getenv("TABLEAU_PAT_NAME")
TABLEAU_PAT_SECRET = os.getenv("TABLEAU_PAT_SECRET")

# 保護する管理者ロールのリスト（これらのロールを持つユーザーは変更・無効化の対象外）
ADMIN_ROLES = ["SiteAdministratorExplorer", "SiteAdministratorCreator", "SiteAdministrator", "ServerAdministrator"]


def load_csv_data(file_path):
    """
    1. CSVファイルを読み込み、扱いやすい辞書形式に変換する関数
    """
    users_data = {}
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # "Sales, Marketing" のような文字列をカンマで分割してリストにする
            raw_group_str = row.get('group', '')
            group_list = []
            for g in raw_group_str.split(','):
                cleaned_group = g.strip() # 前後の余白を削除
                if cleaned_group != "":
                    group_list.append(cleaned_group)

            users_data[row['username']] = {
                'site_role': row['site_role'],
                'groups': group_list
            }
    return users_data


def create_missing_groups(server, csv_users_data, all_tableau_groups):
    """
    2. CSVに書かれているグループがTableau上に無ければ、新しく作成する関数
    """
    # CSVに存在するすべてのグループ名を重複なく集める
    all_csv_group_names = set()
    for user_info in csv_users_data.values():
        for group_name in user_info['groups']:
            all_csv_group_names.add(group_name)

    # 既存のTableauグループ名を小文字にしてリスト化（大文字・小文字の違いによる作成エラーを防ぐため）
    existing_group_names_lower = [name.lower() for name in all_tableau_groups.keys()]

    # CSVのグループがTableau上に存在するかチェック
    for group_name in all_csv_group_names:
        if group_name.lower() not in existing_group_names_lower:
            try:
                new_group = TSC.GroupItem(group_name)
                created_group = server.groups.create(new_group)
                # 新しく作成したグループを既存グループのリスト(辞書)に追加しておく
                all_tableau_groups[created_group.name] = created_group
                print(f"[Group] 新しいグループを作成しました: {created_group.name}")
            except TSC.ServerResponseError as e:
                print(f"[Group Error] グループ '{group_name}' の作成に失敗しました: {e}")

def sync_user_groups(server, tableau_user, csv_groups, all_tableau_groups):
    """
    3. ユーザーの所属グループをCSVの内容と完全に一致させる関数
    """
    # ユーザーが現在所属しているグループを取得
    server.users.populate_groups(tableau_user)
    current_groups = {}
    
    # 修正箇所: TSCライブラリのバグ(400006)を回避するためにTry-Exceptで回す
    try:
        for g in tableau_user.groups:
            current_groups[g.name] = g
    except TSC.ServerResponseError as e:
        if "400006" not in str(e):
            print(f"  [Group Fetch Error] {tableau_user.name} のグループ取得エラー: {e}")
            return # 想定外のエラーの場合は安全のためこのユーザーの同期をスキップ

    # CSVで指定されたグループ名に一致する、Tableau側の「グループオブジェクト」を集める
    target_group_objects = {}
    for csv_g_name in csv_groups:
        for t_name, t_obj in all_tableau_groups.items():
            if csv_g_name.lower() == t_name.lower():
                target_group_objects[t_name] = t_obj

    # ① 不要なグループから外す (All Users 以外で、CSVに書かれていないグループから削除)
    for current_name, current_obj in current_groups.items():
        if current_name == "All Users":
            continue
        if current_name not in target_group_objects:
            try:
                server.groups.remove_user(current_obj, tableau_user.id)
                print(f"  [Group Sync] '{current_name}' から {tableau_user.name} を外しました")
            except TSC.ServerResponseError as e:
                print(f"  [Group Error] '{current_name}' から外すのに失敗: {e}")


    # ② 新しいグループに追加する (現在所属していなくて、CSVに書かれているグループに追加)
    for target_name, target_obj in target_group_objects.items():
        if target_name not in current_groups:
            try:
                server.groups.add_user(target_obj, tableau_user.id)
                print(f"  [Group Sync] '{target_name}' に {tableau_user.name} を追加しました")
            except TSC.ServerResponseError as e:
                # 修正箇所: 409011 (既に参加済み) の場合はエラー出力せずに無視する
                if "409011" not in str(e):
                    print(f"  [Group Error] '{target_name}' への追加に失敗: {e}")


def main_sync(csv_file):
    """
    メインの同期実行プロセス
    """
    print(f"--- 同期開始: {csv_file} ---")
    
    # 1. CSVデータの読み込み
    csv_users_data = load_csv_data(csv_file)

    # 2. Tableauサーバーへのログイン
    tableau_auth = TSC.PersonalAccessTokenAuth(
        token_name=TABLEAU_PAT_NAME,
        personal_access_token=TABLEAU_PAT_SECRET,
        site_id=TABLEAU_SITE_NAME
    )
    server = TSC.Server(TABLEAU_POD_URL, use_server_version=True)

    with server.auth.sign_in(tableau_auth):
        print("[Auth] Tableauサーバーにログインしました。")
        
        # サーバー上の全ユーザーと全グループを取得して辞書にする
        req_options = TSC.RequestOptions(pagesize=1000)
        all_tableau_users = {u.name: u for u in TSC.Pager(server.users, req_options)}
        all_tableau_groups = {g.name: g for g in TSC.Pager(server.groups, req_options)}

        # 3. 足りないグループがあれば作成する
        create_missing_groups(server, csv_users_data, all_tableau_groups)

        # 4. CSVの内容に沿ってユーザーを追加・更新する
        for email, details in csv_users_data.items():
            csv_role = details['site_role']
            csv_groups = details['groups']

            # ユーザーがTableauに存在しない場合は新規追加
            if email not in all_tableau_users:
                try:
                    new_user = TSC.UserItem(email, csv_role)
                    added_user = server.users.add(new_user)
                    all_tableau_users[email] = added_user  # ユーザー一覧を更新
                    print(f"[User Added] ユーザーを追加しました: {email} ({csv_role})")
                except TSC.ServerResponseError as e:
                    print(f"[User Error] ユーザー {email} の追加に失敗: {e}")
                    continue

            tableau_user = all_tableau_users.get(email)
            if not tableau_user:
                continue

            # ロールの更新 (管理者は変更しない)
            is_admin = tableau_user.site_role in ADMIN_ROLES
            if not is_admin and tableau_user.site_role != csv_role:
                try:
                    tableau_user.site_role = csv_role
                    server.users.update(tableau_user)
                    print(f"[User Updated] {email} のロールを {csv_role} に変更しました")
                except TSC.ServerResponseError as e:
                    print(f"[User Error] {email} のロール変更に失敗: {e}")

            # グループ所属の同期
            sync_user_groups(server, tableau_user, csv_groups, all_tableau_groups)

        # 5. CSVに存在しないユーザーを「Unlicensed（無効化）」にする
        for email, tableau_user in all_tableau_users.items():
            is_admin = tableau_user.site_role in ADMIN_ROLES
            is_unlicensed = (tableau_user.site_role == "Unlicensed")
            not_in_csv = (email not in csv_users_data)

            # CSVに存在せず、管理者でもなく、まだUnlicensedではない場合
            if not_in_csv and not is_admin and not is_unlicensed:
                try:
                    tableau_user.site_role = "Unlicensed"
                    server.users.update(tableau_user)
                    print(f"[User Removed] CSVに存在しないため、{email} をUnlicensedにしました")
                except TSC.ServerResponseError as e:
                    print(f"[User Error] {email} の無効化に失敗: {e}")

    print(f"--- 同期完了: {csv_file} ---\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python3 sync_users.py <csvファイル名>")
        sys.exit(1)
    
    csv_filename = sys.argv[1]
    if not os.path.exists(csv_filename):
        print(f"エラー: ファイル '{csv_filename}' が見つかりません。")
        sys.exit(1)
        
    main_sync(csv_filename)