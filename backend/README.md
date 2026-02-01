# CoTask Agent Backend

## Phase 2 実装完了

Phase 2では、LangGraphによる対話フローとSQLite/SQLAlchemyによるチャット履歴の永続化を実装しました。

### セットアップ

1. 依存関係のインストール:
```bash
uv sync
```

2. 環境変数の設定:
`.env.example`を`.env`にコピーし、`OPENAI_API_KEY`を設定してください。

```bash
cp .env.example .env
# .envファイルを編集してOPENAI_API_KEYを設定
```

3. サーバーの起動:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### API エンドポイント

- `POST /api/chat`: チャットメッセージを送信し、AI応答を取得
- `GET /api/chat/sessions/{session_id}`: 指定されたセッションのチャット履歴を取得
- `POST /api/chat/sessions`: 新しいチャットセッションを作成

### データベース

SQLiteデータベース（`cotask.db`）にチャットセッションとメッセージが保存されます。
ブラウザをリロードしても、ローカルストレージに保存されたセッションIDから履歴を復元できます。
