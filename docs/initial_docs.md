# 最終製品仕様書：AutoGen Multi-Task Orchestrator (Full Specs)

## 1. システム概要

Docker Composeで一括起動し、OpenAI/ClaudeのAPIを使い分けて複数の自律タスクを並列実行するツール。AutoGenの「設計(Architect)」と「実行(Executor)」の2エージェント体制でタスクを完遂します。

## 2. 確定した機能要件

- **タスク並列管理**: フロントエンドで最大同時実行数を設定（デフォルト3）。制限を超えたタスクはキュー待機。
- **モデル選択**: タスク作成時にUI上で OpenAI (GPT-4o等) か Anthropic (Claude 3.5 Sonnet等) を選択可能。
- **コード実行環境**: ホストのDockerを利用した「独立コンテナ」で実行。安全性を確保。
- **成果物管理**: エージェントが生成したファイルは、バックエンド経由でフロントエンドからダウンロード可能。
- **永続化**: タスク履歴、対話ログ、成果物パスをSQLiteで保存。

## 3. テクニカルスタック

- **Frontend**: Next.js (TypeScript) + Tailwind CSS + Lucide React (アイコン)
- **Backend**: FastAPI (Python) + SQLAlchemy (SQLite)
- **Agent**: AutoGen (Architect & Executor の GroupChat)
- **Infrastructure**: Docker Compose (Frontend, Backend, Code-Runtime)

## 4. 主要な実装コンポーネントの役割

### ① AutoGen エージェント構成

- **Architect Agent**: ユーザーの要望を分析し、実行コードや手順を作成する。
- **Executor Agent**: 指定された独立コンテナ内でコードを実行し、結果を報告する。
- **成果物の扱い**: 実行コンテナ内の `outputs/` フォルダをホスト側の `data/artifacts/{task_id}/` にマウントし、ユーザーが取得できるようにします。

### ② ワークフロー

1. **UI**: タスク名、依頼内容、使用モデルを選択して「開始」。
2. **Backend**: `task_id` を発行し、同時実行枠を確認。空きがあればAutoGenセッションを開始。
3. **Side panel**: タスクが「Running」になり、リアルタイムでAutoGenの内部ログが流れる。
4. **Completion**: エージェントが「TERMINATE」を宣言したら終了。生成されたファイルへのリンクをUIに表示。

## 5. プロジェクト構造（最終案）

```
.
├── .env                    # 各種APIキー、デフォルト並列数設定
├── docker-compose.yml
├── data/
│   ├── sqlite.db           # タスク・ログ保存用
│   └── artifacts/          # エージェントが生成したファイル群
├── frontend/               # Next.js アプリ
└── backend/
    ├── pyproject.toml      # uvによるパッケージ管理
    ├── main.py             # FastAPI エンドポイント
    ├── orchestrator.py     # AutoGen 制御 (並列実行管理)
    └── agents/             # エージェント定義 (Architect/Executor)
```
