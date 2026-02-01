# API仕様書

## 概要

CoTask Agent Backend APIの仕様書です。このAPIはタスク管理、並列実行制御、成果物管理を提供します。

**ベースURL**: `http://localhost:8000` (開発環境)

## 認証

現在のバージョンでは認証は実装されていません。将来的に追加予定です。

## エンドポイント一覧

### ヘルスチェック

#### GET `/`
ルートエンドポイント

**レスポンス**
```json
{
  "message": "CoTask Agent API",
  "version": "0.1.0"
}
```

#### GET `/health`
ヘルスチェックエンドポイント

**レスポンス**
```json
{
  "status": "healthy"
}
```

---

### タスク管理

#### POST `/api/tasks`
新しいタスクを作成します。

**リクエストボディ**
```json
{
  "name": "タスク名",
  "description": "タスクの説明",
  "model_provider": "openai" | "anthropic",
  "model_name": "gpt-4o" | "claude-3-5-sonnet-20241022"
}
```

**レスポンス** (201 Created)
```json
{
  "id": "uuid",
  "name": "タスク名",
  "description": "タスクの説明",
  "model_provider": "openai",
  "model_name": "gpt-4o",
  "status": "pending",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "started_at": null,
  "completed_at": null,
  "error_message": null,
  "artifact_path": "/path/to/artifacts"
}
```

**エラー**
- `400 Bad Request`: リクエストボディが不正
- `422 Unprocessable Entity`: バリデーションエラー

---

#### GET `/api/tasks`
タスク一覧を取得します。

**クエリパラメータ**
- `skip` (int, デフォルト: 0): スキップする件数
- `limit` (int, デフォルト: 100): 取得する最大件数
- `status` (string, オプション): フィルタリングするステータス (`pending`, `running`, `completed`, `failed`, `cancelled`)

**レスポンス** (200 OK)
```json
{
  "tasks": [
    {
      "id": "uuid",
      "name": "タスク名",
      "description": "タスクの説明",
      "model_provider": "openai",
      "model_name": "gpt-4o",
      "status": "running",
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T00:00:00",
      "started_at": "2024-01-01T00:01:00",
      "completed_at": null,
      "error_message": null,
      "artifact_path": "/path/to/artifacts"
    }
  ],
  "total": 1
}
```

---

#### GET `/api/tasks/{task_id}`
特定のタスクの詳細を取得します。

**パスパラメータ**
- `task_id` (string): タスクID

**レスポンス** (200 OK)
```json
{
  "id": "uuid",
  "name": "タスク名",
  "description": "タスクの説明",
  "model_provider": "openai",
  "model_name": "gpt-4o",
  "status": "completed",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:05:00",
  "started_at": "2024-01-01T00:01:00",
  "completed_at": "2024-01-01T00:05:00",
  "error_message": null,
  "artifact_path": "/path/to/artifacts"
}
```

**エラー**
- `404 Not Found`: タスクが見つからない

---

#### PATCH `/api/tasks/{task_id}/status`
タスクのステータスを更新します。

**パスパラメータ**
- `task_id` (string): タスクID

**リクエストボディ**
```json
{
  "status": "running" | "completed" | "failed" | "cancelled",
  "error_message": "エラーメッセージ（オプション）"
}
```

**レスポンス** (200 OK)
```json
{
  "id": "uuid",
  "name": "タスク名",
  "description": "タスクの説明",
  "model_provider": "openai",
  "model_name": "gpt-4o",
  "status": "failed",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:05:00",
  "started_at": "2024-01-01T00:01:00",
  "completed_at": "2024-01-01T00:05:00",
  "error_message": "エラーメッセージ",
  "artifact_path": "/path/to/artifacts"
}
```

**エラー**
- `404 Not Found`: タスクが見つからない
- `400 Bad Request`: 無効なステータス

---

#### DELETE `/api/tasks/{task_id}`
タスクを削除します。

**パスパラメータ**
- `task_id` (string): タスクID

**レスポンス** (204 No Content)

**エラー**
- `404 Not Found`: タスクが見つからない

---

### タスクログ

#### GET `/api/tasks/{task_id}/logs`
タスクのログを取得します。

**パスパラメータ**
- `task_id` (string): タスクID

**クエリパラメータ**
- `skip` (int, デフォルト: 0): スキップする件数
- `limit` (int, デフォルト: 1000): 取得する最大件数

**レスポンス** (200 OK)
```json
[
  {
    "id": 1,
    "task_id": "uuid",
    "timestamp": "2024-01-01T00:00:00",
    "role": "user",
    "content": "ログの内容"
  },
  {
    "id": 2,
    "task_id": "uuid",
    "timestamp": "2024-01-01T00:01:00",
    "role": "assistant",
    "content": "ログの内容"
  }
]
```

**エラー**
- `404 Not Found`: タスクが見つからない

---

#### POST `/api/tasks/{task_id}/logs`
タスクにログエントリを追加します。

**パスパラメータ**
- `task_id` (string): タスクID

**クエリパラメータ**
- `role` (string): ログの役割 (`user`, `assistant`, `system` など)
- `content` (string): ログの内容

**レスポンス** (200 OK)
```json
{
  "id": 1,
  "task_id": "uuid",
  "timestamp": "2024-01-01T00:00:00",
  "role": "user",
  "content": "ログの内容"
}
```

**エラー**
- `404 Not Found`: タスクが見つからない
- `400 Bad Request`: パラメータが不正

---

### 成果物管理

#### GET `/api/tasks/{task_id}/artifacts`
タスクの成果物一覧を取得します。

**パスパラメータ**
- `task_id` (string): タスクID

**レスポンス** (200 OK)
```json
{
  "artifacts": [
    {
      "name": "output.txt",
      "path": "output.txt",
      "size": 1024
    },
    {
      "name": "result.json",
      "path": "subdir/result.json",
      "size": 2048
    }
  ]
}
```

**エラー**
- `404 Not Found`: タスクが見つからない

---

#### GET `/api/tasks/{task_id}/artifacts/{file_path}`
特定の成果物ファイルをダウンロードします。

**パスパラメータ**
- `task_id` (string): タスクID
- `file_path` (string): ファイルパス（パスパラメータとして）

**レスポンス** (200 OK)
- Content-Type: `application/octet-stream`
- ファイルのバイナリデータ

**エラー**
- `404 Not Found`: タスクまたはファイルが見つからない
- `403 Forbidden`: アクセスが拒否された（セキュリティチェック）

**例**
```
GET /api/tasks/123e4567-e89b-12d3-a456-426614174000/artifacts/output.txt
GET /api/tasks/123e4567-e89b-12d3-a456-426614174000/artifacts/subdir/result.json
```

---

### 設定管理

#### GET `/api/config`
現在の設定を取得します。

**レスポンス** (200 OK)
```json
{
  "max_concurrent_tasks": 3,
  "default_model_provider": null,
  "default_model_name": null
}
```

---

#### PATCH `/api/config`
設定を更新します。

**クエリパラメータ**
- `max_concurrent_tasks` (int, オプション): 最大同時実行タスク数

**レスポンス** (200 OK)
```json
{
  "max_concurrent_tasks": 5,
  "default_model_provider": null,
  "default_model_name": null
}
```

---

### 統計情報

#### GET `/api/stats`
システムの統計情報を取得します。

**レスポンス** (200 OK)
```json
{
  "total_tasks": 100,
  "running_tasks": 2,
  "pending_tasks": 5,
  "completed_tasks": 90,
  "failed_tasks": 3,
  "orchestrator_running": 2,
  "queue_size": 0,
  "max_concurrent_tasks": 3
}
```

---

## データモデル

### TaskStatus
タスクのステータスを表す列挙型です。

- `pending`: 待機中
- `running`: 実行中
- `completed`: 完了
- `failed`: 失敗
- `cancelled`: キャンセル

### ModelProvider
AIモデルのプロバイダーを表す列挙型です。

- `openai`: OpenAI
- `anthropic`: Anthropic

### Task
タスクのデータモデルです。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| id | string | タスクID (UUID) |
| name | string | タスク名 |
| description | string | タスクの説明 |
| model_provider | ModelProvider | AIモデルのプロバイダー |
| model_name | string | 使用するモデル名 |
| status | TaskStatus | タスクのステータス |
| created_at | datetime | 作成日時 |
| updated_at | datetime | 更新日時 |
| started_at | datetime | 開始日時（null可能） |
| completed_at | datetime | 完了日時（null可能） |
| error_message | string | エラーメッセージ（null可能） |
| artifact_path | string | 成果物のパス（null可能） |

### TaskLog
タスクログのデータモデルです。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| id | int | ログID |
| task_id | string | タスクID |
| timestamp | datetime | タイムスタンプ |
| role | string | ログの役割（user, assistant, systemなど） |
| content | string | ログの内容 |

---

## エラーレスポンス

すべてのエラーレスポンスは以下の形式です：

```json
{
  "detail": "エラーメッセージ"
}
```

### HTTPステータスコード

- `200 OK`: リクエスト成功
- `201 Created`: リソース作成成功
- `204 No Content`: リクエスト成功（レスポンスボディなし）
- `400 Bad Request`: リクエストが不正
- `403 Forbidden`: アクセスが拒否された
- `404 Not Found`: リソースが見つからない
- `422 Unprocessable Entity`: バリデーションエラー
- `500 Internal Server Error`: サーバー内部エラー

---

## 並列実行制御

システムは最大同時実行タスク数を制御します。デフォルトは3タスクです。

- タスク作成時、同時実行数が上限に達している場合、タスクは`pending`ステータスで待機します
- 実行中のタスクが完了すると、待機中のタスクが自動的に開始されます（将来実装予定）
- 最大同時実行数は`/api/config`エンドポイントで変更可能です

---

## 成果物の保存場所

成果物は以下のディレクトリ構造で保存されます：

```
data/
└── artifacts/
    └── {task_id}/
        └── [生成されたファイル]
```

各タスクには専用のディレクトリが割り当てられ、その中に生成されたファイルが保存されます。

---

## 注意事項

1. **セキュリティ**: 現在のバージョンでは認証が実装されていません。本番環境では適切な認証・認可を実装してください。

2. **CORS**: 開発環境ではすべてのオリジンからのアクセスを許可しています。本番環境では適切なCORS設定を行ってください。

3. **ファイルパス**: 成果物のダウンロード時、パストラバーサル攻撃を防ぐため、セキュリティチェックが実装されています。

4. **データベース**: SQLiteを使用しています。本番環境ではPostgreSQLなどの本格的なデータベースの使用を推奨します。

---

## 開発環境での起動

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

APIドキュメント（Swagger UI）は以下のURLで確認できます：
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`
