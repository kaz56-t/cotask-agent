# CoTask Agent - AutoGen Multi-Task Orchestrator

Docker Composeで一括起動し、OpenAI/ClaudeのAPIを使い分けて複数の自律タスクを並列実行するツール。

## セットアップ

### 1. 環境変数の設定

`.env`ファイルを作成し、以下の環境変数を設定してください：

```bash
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Anthropic API Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Langfuse Configuration (Optional)
# LangfuseのAPI KEYが設定されている場合、LLMのトラッキングが可能です
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-your-public-key-here
LANGFUSE_SECRET_KEY=sk-your-secret-key-here

# Task Configuration
MAX_CONCURRENT_TASKS=3

# Database Configuration
DATABASE_URL=sqlite:///./data/sqlite.db
```

### 2. Docker Composeで起動

```bash
docker-compose up -d
```

### 3. サービスへのアクセス

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## プロジェクト構造

```
.
├── docker-compose.yml          # メインアプリケーションのDocker Compose設定
├── .env                        # 環境変数（要作成）
├── data/                       # データ永続化
│   ├── sqlite.db              # SQLiteデータベース
│   └── artifacts/             # エージェントが生成したファイル
├── frontend/                   # Next.js アプリケーション
│   ├── Dockerfile
│   └── package.json
└── backend/                    # FastAPI バックエンド
    ├── Dockerfile
    ├── pyproject.toml
    ├── main.py
    ├── orchestrator.py
    └── models.py
```

## 開発

### バックエンドの開発

バックエンドコードは`./backend`ディレクトリにマウントされているため、コードを変更すると自動的にリロードされます。

### フロントエンドの開発

フロントエンドコードは`./frontend`ディレクトリにマウントされているため、コードを変更すると自動的にリロードされます。

### ログの確認

```bash
# すべてのサービスのログ
docker-compose logs -f

# 特定のサービスのログ
docker-compose logs -f backend
docker-compose logs -f frontend
```

### サービスの停止

```bash
docker-compose down
```

### データの削除（注意：すべてのデータが削除されます）

```bash
docker-compose down -v
rm -rf data/
```

## 注意事項

- バックエンドコンテナはホストのDockerソケット（`/var/run/docker.sock`）にアクセスして、コード実行用の独立コンテナを作成します
- データは`./data`ディレクトリに永続化されます
- 環境変数は`.env`ファイルで管理してください
