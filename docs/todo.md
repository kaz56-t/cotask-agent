# TODO
## Infra
- github actions

## Agent
- 実行可能なタスクの選択肢を増やす
- 簡単なタスクはExecutorではなくChat Agentで実行する
- max_iterationsを動的に設定

## UIUX
- 過去Taskの削除
- タスクのテンプレ化
- タスク実施結果の再利用


## Improve Agent

### 実装方針：ハイブリッドアプローチ（段階的移行）

現在のPythonコード生成中心のアプローチから、タスクタイプに応じて最適なAgentを選択する方式へ段階的に移行する。

**現状の問題点**:
- すべてのタスクがPythonコード生成→実行のパターン
- 単純なタスクでもコード生成のオーバーヘッドが発生
- 検索、RAG、テキスト生成などは専用ツールの方が効率的

**目標アーキテクチャ**:
- タスクタイプを自動判定し、最適なAgentを選択
- 専用Agent: SearchAgent, TextAgent, ScrapingAgent, RAGAgent
- 既存のCodeAgent（Architect+Executor）は複雑なコード生成タスク用に継続使用

### Phase 0: テスト用APIエンドポイントの追加

- [x] Swaggerだけでタスクの要件定義をスキップしてタスクの実行のみをテストする機構を追加
  - `POST /api/tasks/test-execute` エンドポイントを作成 ✅
  - タスク名、説明、モデル設定を直接指定して実行可能 ✅
  - Chat Sessionや要件定義をスキップして即座にTask Agentを実行 ✅
  - 開発・デバッグ時のテスト効率化を目的とする ✅
  - `run_task_background`関数を修正してsession_idがnullの場合の処理を追加 ✅

### Phase 1: タスク分類機能の実装

- [ ] `complexity_analyzer.py`を拡張し、タスクタイプ判定機能を追加
  - タスクタイプ: `code_generation`, `web_search`, `text_generation`, `scraping`, `rag`, `simple_text`
  - LLMベースの分類（既存のcomplexity分析と統合）
- [ ] `AgentState`に`task_type`フィールドを追加
- [ ] タスク分類結果をDBに保存（`Task.task_type`カラム追加）

### Phase 2: 専用Agentの実装

- [ ] **TextAgent**: テキスト生成・編集タスク用
  - コード生成不要なシンプルなテキスト処理
  - メール作成、レポート生成、要約など
  - LangGraphのシンプルな1ノードワークフロー
  
- [ ] **SearchAgent**: Web検索タスク用
  - Tavily APIやSerper APIなどの検索ツール統合
  - 検索結果の要約・整理
  - LangGraphの2ノードワークフロー（検索→要約）

- [ ] **ScrapingAgent**: Webスクレイピングタスク用
  - Playwright/BeautifulSoup統合
  - 動的コンテンツの取得
  - LangGraphの2ノードワークフロー（スクレイピング→処理）

- [ ] **RAGAgent**: ドキュメント検索・質問応答用
  - ベクトルDB統合（Chroma/FAISS）
  - ドキュメントのインデックス化
  - LangGraphの2ノードワークフロー（検索→生成）

### Phase 3: Agentルーターの実装

- [ ] `agent_router.py`を作成
  - タスクタイプに応じて適切なワークフローを返す関数
  - `route_task(task_type: str, task_description: str) -> Workflow`
- [ ] `create_workflow()`をリファクタリング
  - ルーター経由でワークフローを生成
  - 既存のCodeAgentワークフローは`create_code_workflow()`として分離
- [ ] `run_task_background()`でルーターを使用

### Phase 4: 既存機能の改善

- [ ] 簡単なタスクはExecutorではなくChat Agentで実行する（既存TODO）
- [ ] `max_iterations`を動的に設定（既存TODO）
  - タスクタイプと複雑度に応じて調整
  - シンプルなタスクは1回、複雑なタスクは3-5回

### 実装の優先順位

1. **最優先**: Phase 0（テスト用APIエンドポイント）
2. **即時**: Phase 1（タスク分類機能）
3. **短期**: Phase 2のTextAgent（最もシンプルで効果的）
4. **中期**: Phase 2のSearchAgent、Phase 3（ルーター）
5. **長期**: Phase 2の残り（ScrapingAgent, RAGAgent）

### 参考アーキテクチャ

```
Task → TaskClassifier → AgentRouter → [TextAgent | SearchAgent | CodeAgent | ...]
                                                      ↓
                                              Workflow Execution
                                                      ↓
                                              Result & Artifacts
```