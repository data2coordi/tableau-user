#!/bin/bash

# .env から環境変数を読み込み
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

CSV_FILE="${1:-day2.csv}"

if [ ! -f "$CSV_FILE" ]; then
  echo "[エラー] CSVファイル '${CSV_FILE}' が存在しません。"
  exit 1
fi

echo "========== [1/4] CSV確認 =========="
cat "$CSV_FILE"
echo ""
echo "-----------------------------------"

echo "========== [2/4] Tableau Cloud 認証 =========="
tabcmd login \
  --server "$TABLEAU_POD_URL" \
  --site "$TABLEAU_SITE_NAME" \
  --token-name "$TABLEAU_PAT_NAME" \
  --token-value "$TABLEAU_PAT_SECRET"

echo "========== [3/4] ユーザーの一括プロビジョニング =========="
TEMP_USERS="temp_all_users.csv"
awk -F',' 'NR>1 {u=$1; gsub(/\r/, "", u); gsub(/^[ \t]+|[ \t]+$/, "", u); if(u!="") print u}' "$CSV_FILE" | sort -u > "$TEMP_USERS"

tabcmd createsiteusers "$TEMP_USERS" -r "Explorer" --continue-if-exists

echo "========== [4/4] グループの作成とメンバー割り当て =========="
# ★修正箇所: 変数名をシステム予約の GROUPS から TARGET_GROUPS に変更
TARGET_GROUPS=$(awk -F',' 'NR>1 {g=$2; gsub(/\r/, "", g); gsub(/^[ \t]+|[ \t]+$/, "", g); if(g!="" && g!="group") print g}' "$CSV_FILE" | sort -u)

echo "検出されたグループ:"
echo "$TARGET_GROUPS" | sed 's/^/  - /'

echo "$TARGET_GROUPS" | while read -r group_name; do
  if [ -n "$group_name" ]; then
    echo "--- グループ処理: ${group_name} ---"
    
    # 1. グループ作成
    tabcmd creategroup "$group_name" --continue-if-exists || true
    
    # 2. 該当グループに所属するユーザーのみ抽出
    TEMP_GROUP_USERS="temp_${group_name}.csv"
    awk -F',' -v target="$group_name" '
    NR>1 {
      u=$1; g=$2;
      gsub(/\r/, "", u); gsub(/^[ \t]+|[ \t]+$/, "", u);
      gsub(/\r/, "", g); gsub(/^[ \t]+|[ \t]+$/, "", g);
      if (g == target && u != "") print u;
    }' "$CSV_FILE" > "$TEMP_GROUP_USERS"
    
    # 3. ユーザーをグループに追加
    tabcmd addusers "$group_name" --users "$TEMP_GROUP_USERS" || true
    
    rm -f "$TEMP_GROUP_USERS"
  fi
done

# 後処理
rm -f "$TEMP_USERS"

echo "========== サインアウト =========="
tabcmd logout
echo "すべての同期処理が正常に完了しました。"