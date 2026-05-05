**[日本語](#databricks-agent-chat-テンプレート)** | **[English](#databricks-agent-chat-template)**

---

<a href="https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app">
  <h1 align="center">Databricks Agent Chat テンプレート</h1>
</a>

<p align="center">
    Databricks Agent Serving エンドポイントと対話するためのチャットアプリケーションテンプレートです。ExpressJS、React、Vercel AI SDK、Databricks 認証、およびオプションの Lakebase（データベース）統合を使用して構築されています。
</p>

<p align="center">
  <a href="#機能"><strong>機能</strong></a> ·
  <a href="#ローカルでの実行"><strong>ローカルでの実行</strong></a> ·
  <a href="#デプロイ"><strong>デプロイ</strong></a> ·
  <a href="#オプションのチャットui機能"><strong>オプション機能</strong></a>
</p>
<br/>

このテンプレートは、Databricks 上にデプロイされたカスタムコードエージェントおよび Agent Bricks 向けの完全に機能するチャットアプリを提供しますが、その他のユースケースにはいくつかの[既知の制限事項](#既知の制限事項)があります。これらの制限事項の解消に向けた作業が進行中です。

## 機能

- **Databricks Agent およびファウンデーションモデル統合**: Databricks Agent Serving エンドポイントおよび Agent Bricks への直接接続
- **Databricks 認証**: Databricks 認証を使用してチャットアプリのエンドユーザーを識別し、会話を安全に管理します
- **永続的なチャット履歴（オプション）**: Databricks Lakebase（Postgres）を活用して会話を保存し、ガバナンスとレイクハウスとの緊密な統合を実現します。データベースなしのエフェメラルモードでも実行できます
- **ユーザーフィードバック収集（オプション）**: アシスタントメッセージに対するサムズアップ/ダウンフィードバックを、基盤となるトレースの MLflow アセスメントとして保存します。MLflow エクスペリメントリソースの設定が必要です

## 前提条件

1. **Databricks サービングエンドポイント**: チャット対象の Agent Bricks またはカスタムエージェントサービングエンドポイントを含む Databricks ワークスペースへのアクセスが必要です
2. **Databricks 認証の設定**
   - 最新バージョンの [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/install.html) をインストールしてください。macOS の場合は以下の方法でインストールできます：
   ```bash
   brew install databricks
   brew upgrade databricks && databricks -v
   ```
   - 以下を実行して認証を設定します。
     下記のスニペットで `DATABRICKS_CONFIG_PROFILE` は、認証を設定する Databricks CLI プロファイルの名前です。必要に応じて、`dev_workspace` など任意の名前に変更できます。
   ```bash
     export DATABRICKS_CONFIG_PROFILE='chatbot_template'
     databricks auth login --profile "$DATABRICKS_CONFIG_PROFILE"
   ```

## デプロイ

このプロジェクトには、必要なすべてのリソースの作成と管理を自動化する [Databricks Asset Bundle (DAB)](https://docs.databricks.com/aws/en/dev-tools/bundles/apps-tutorial) 設定が含まれています。

1. **リポジトリのクローン**:
   ```bash
   git clone https://github.com/databricks/app-templates
   cd e2e-chatbot-app-next
   ```
2. **Databricks 認証**: [前提条件](#前提条件)に記載されているように認証が設定されていることを確認してください。
3. **サービングエンドポイントの指定と databricks.yml の TODO 対応**: `databricks.yml` 内の TODO に対応し、`serving_endpoint_name` のデフォルト値をチャット対象のカスタムコードエージェントまたは Agent Bricks エンドポイントの名前に設定します。オプションのコメントアウトされたセクションで以下を有効にできます：
   - **永続的なチャット履歴** — 2つのオプションの `TODO` データベースブロックのコメントを解除して、Lakebase データベースをプロビジョニングおよびバインドします。詳細は[データベースモード](#データベースモード)を参照してください。**ヒント:** `./scripts/quickstart.sh` を実行すると自動で設定できます。
   - **ユーザーフィードバック収集** — オプションの `TODO` エクスペリメントブロックのコメントを解除し、エクスペリメント ID を設定します。データベースも必要です（両方のデータベース `TODO` ブロックのコメントを解除する必要があります）。詳細は[フィードバック収集](#フィードバック収集)を参照してください。**ヒント:** `./scripts/quickstart.sh` を実行するとデータベースとフィードバックの両方を自動で設定できます。

   - 注意: [Agent Bricks Multi-Agent Supervisor](https://docs.databricks.com/aws/en/generative-ai/agent-bricks/multi-agent-supervisor) を使用する場合は、MAS がオーケストレーションする基盤エージェントに対してアプリのサービスプリンシパルに `CAN_QUERY` 権限を追加で付与する必要があります。これは、該当するエージェントサービングエンドポイントを `databricks.yml` のリソースとして追加することで実現できます（`databricks.yml` 内の NOTE を参照）
4. **バンドル設定の検証**:

   ```bash
   databricks bundle validate
   ```

5. **バンドルのデプロイ**。初回デプロイはリソースのプロビジョニング（特にデータベースが有効な場合）に数分かかる場合がありますが、以降のデプロイは高速です：

   ```bash
   databricks bundle deploy
   ```

   これにより以下が作成されます：

   - 起動可能な **App リソース**
   - **Lakebase データベースインスタンス**（データベースリソースのコメントが解除されている場合のみ）

6. **アプリの起動**:

   ```bash
   databricks bundle run databricks_chatbot
   ```

7. **デプロイサマリーの確認**（デプロイの問題をデバッグする際に便利です）：
   ```bash
   databricks bundle summary
   ```

### デプロイターゲット

バンドルは複数の環境をサポートしています：

- **dev**（デフォルト）: 開発環境
- **staging**: テスト用のステージング環境
- **prod**: 本番環境

特定のターゲットにデプロイするには：

```bash
databricks bundle deploy -t staging --var serving_endpoint_name="your-endpoint"
```

## ローカルでの実行

### クイックスタート（推奨）

自動化されたクイックスタートスクリプトを使用して、最速のセットアップを実現できます：

1. **リポジトリのクローン**:

   ```bash
   git clone https://github.com/databricks/app-templates
   cd e2e-chatbot-app-next
   ```

2. **クイックスタートスクリプトの実行**:

   ```bash
   ./scripts/quickstart.sh
   ```

   クイックスタートスクリプトは以下を行います：
   - **前提条件のインストール** - jq、nvm、Node.js 20、Databricks CLI を自動インストール
   - **認証の設定** - Databricks CLI プロファイルの選択または作成を支援
   - **サービングエンドポイントの設定** - エンドポイント名の入力を促し、存在を検証
   - **データベースの設定（オプション）** - 永続的なチャット履歴またはエフェメラルモードを選択
   - **Databricks へのデプロイ（オプション）** - オプションでリソースをデプロイしデータベースをプロビジョニング
   - **ローカル環境の設定** - `.env` を自動的に作成・設定
   - **マイグレーションの実行** - データベースが有効な場合、データベーススキーマをセットアップ

   スクリプトはデータベースのプロビジョニング待機や接続情報の設定を含む、セットアッププロセス全体を自動的に処理します。

3. **アプリケーションの起動**:

   便利なスクリプトを使用する場合：
   ```bash
   ./scripts/start-app.sh
   ```

   または手動で：
   ```bash
   npm install  # 依存関係のインストール/更新
   npm run dev  # 開発サーバーの起動
   ```

   アプリは [localhost:3000](http://localhost:3000)（フロントエンド）と [localhost:3001](http://localhost:3001)（バックエンド）で起動します

   **ヒント:** `start-app.sh` スクリプトは、初期セットアップ後にアプリを素早く起動するのに便利です。開発サーバーの起動前に依存関係が最新であることを確認します。

### 手動セットアップ（代替方法）

環境を手動で設定する場合：

1. **クローンとインストール**:

   ```bash
   git clone https://github.com/databricks/app-templates
   cd e2e-chatbot-app-next
   npm install
   ```

2. **環境変数の設定**:

   ```bash
   cp .env.example .env
   ```

   `.env` 内の TODO に対応し、Databricks CLI プロファイルとデータベース接続情報を指定してください。

3. **アプリケーションの実行**:

   ```bash
   npm run dev
   ```

   アプリは [localhost:3000](http://localhost:3000) で起動します

### オプションのチャットUI機能

チャット UI は `databricks.yml` を更新することで有効にできる2つのオプション機能をサポートしています：

### ユーザーフィードバック

ユーザーはアシスタントの応答にサムズアップ/ダウンで評価できます。フィードバックは基盤となるトレースの [MLflow アセスメント](https://docs.databricks.com/aws/en/generative-ai/agent-evaluation/assessments)として保存され、MLflow Experiment Tracking UI で簡単に確認・対応できます。

フィードバックは**デフォルトで無効**です。設定手順は[フィードバック収集](#フィードバック収集)を参照してください。

> **注意:** 会話型エージェントテンプレート（例: `agent-openai-agents-sdk`、`agent-langgraph`）を使用している場合、それらの `databricks.yml` は既に MLflow エクスペリメントを作成・バインドしているため、`databricks bundle deploy` 後に追加設定なしでフィードバック機能が自動的に動作します。

### 永続的なチャット履歴

デフォルトでは、会話メッセージはメモリに保存され、サーバーの再起動時に失われます。セッション間でチャット履歴を永続化するには、`databricks.yml` で Lakebase データベースをバインドしてください。

設定手順は[データベースモード](#データベースモード)を参照してください。

---

## データベースモード

アプリケーションは2つの動作モードをサポートしています：

#### 永続モード（データベースあり）

データベース環境変数が設定されている場合のデフォルトモードです。このモードでは：

- チャット会話が Postgres/Lakebase に保存されます
- ユーザーはサイドバーからチャット履歴にアクセスできます
- 会話がセッション間で永続化されます
- データベース接続が必要です（POSTGRES_URL または PGDATABASE 環境変数）

#### エフェメラルモード（データベースなし）

アプリケーションはデータベースなしでも実行できます。このモードでは：

- チャット会話は通常どおり動作しますが、**保存されません**
- サイドバーに「チャット履歴はありません」と表示されます
- ヘッダーに小さな「Ephemeral」インジケーターが表示されます
- ユーザーは AI との会話が可能ですが、ページ更新時に履歴が失われます

#### データベースモードの選択

データベース環境変数が設定されていない場合、アプリケーションはデフォルトで「エフェメラルモード」になります。
永続モードで実行するには、環境に以下のデータベース変数を設定してください：

```bash
# ローカル開発に便利
POSTGRES_URL=...

# または

# Databricks Apps 使用時は自動的に処理されます
PGUSER=...
PGPASSWORD=...
PGDATABASE=...
PGHOST=...
```

アプリはデータベース設定の有無を検出し、適切なモードで自動的に実行されます。

#### インストール後のデータベース有効化

データベースサポートなし（エフェメラルモード）でテンプレートをインストールした後、永続的なチャット履歴を追加する場合は、クイックスタートスクリプトを再実行できます：

```bash
./scripts/quickstart.sh
```

永続的なチャット履歴の有効化を求められた際に「Yes」を選択してください。スクリプトは以下を行います：
- `databricks.yml` 内の必要なデータベースセクションのコメントを解除
- オプションで Lakebase データベースインスタンスをデプロイ
- `.env` ファイルにデータベース接続情報を設定
- データベースがプロビジョニングされている場合、データベースマイグレーションを実行
- 正しいデータベース設定でローカル環境をセットアップ

スクリプトは以下を含むすべての設定を自動的に処理します：
- Databricks ワークスペースと認証の検出
- ターゲット環境に対応する正しいデータベースインスタンス名の算出
- プロビジョニング後のデータベースホスト（PGHOST）の取得
- 正しい値での環境変数の更新

**手動手順（代替方法）：**

データベースを手動で有効にする場合：

1. **`databricks.yml` の編集** - 両方のデータベースセクションのコメントを解除：
   - データベースインスタンスリソース（`chatbot_lakebase`）18行目付近
   - データベースリソースバインディング（`- name: database`）41行目付近

2. **データベースのデプロイ**:
   ```bash
   databricks bundle deploy
   ```
   （初回デプロイはプロビジョニングに数分かかります）

3. **`.env`** にデータベース変数を設定：
   ```bash
   PGUSER=your-databricks-username
   PGHOST=your-postgres-host  # 取得方法: ./scripts/get-pghost.sh
   PGDATABASE=databricks_postgres
   PGPORT=5432
   ```

4. **データベースマイグレーションの実行**:
   ```bash
   npm run db:migrate
   ```

## フィードバック収集

チャットアプリはアシスタントメッセージに対するオプションのサムズアップ/ダウンフィードバックをサポートしています。有効にすると、フィードバックはエージェントエンドポイントが出力するトレースの [MLflow アセスメント](https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app)として保存され、MLflow UI で簡単に確認・対応できます。

フィードバックは**デフォルトで無効**です。設定されていない場合、ヘッダーに「Feedback disabled」バッジが表示されます。

> **注意:** フィードバック投票の永続化（ページリロード時のサムズアップ/ダウン状態の復元）にはデータベースが必要です。クイックスタートスクリプトを使用すれば、両方の機能を一度に有効にできます。

### 推奨: クイックスタートスクリプトの使用

フィードバック（および永続的なチャット履歴）を有効にする最も簡単な方法は、対話型セットアップスクリプトを実行することです：

```bash
./scripts/quickstart.sh
```

スクリプトは自動的に以下を行います：
1. サービングエンドポイントに紐づく MLflow エクスペリメント ID を検索
2. `databricks.yml` 内のフィードバック `TODO` ブロックのコメントを解除して設定（`experiment_id` の設定）し、`app.yaml` 内の `MLFLOW_EXPERIMENT_ID` 環境変数を設定
3. `databricks.yml` 内の両方のデータベース `TODO` ブロックのコメントを解除して Lakebase データベースをプロビジョニングおよびバインド

スクリプト完了後、`databricks bundle deploy` を実行して変更を適用してください。

### 手動設定

手動で設定する場合：

**ステップ 1 — エクスペリメント ID の確認**

```bash
# カスタムコードエージェントまたは Agent Bricks サービングエンドポイントの場合
npx tsx scripts/get-experiment-id.ts --endpoint <your-endpoint-name>

# Agent Bricks Knowledge Assistant または Multi-Agent Supervisor の場合
npx tsx scripts/get-experiment-id.ts --agent-brick <agent-brick-name>
```

**ステップ 2 — `databricks.yml` の設定**

両方のデータベース `TODO` ブロック（投票の永続化に必要）とフィードバック `TODO` ブロックのコメントを解除し、ステップ 1 のエクスペリメント ID を設定します：

```yaml
- name: experiment
  description: "MLflow experiment for collecting user feedback"
  experiment:
    experiment_id: "your-experiment-id"
    permission: CAN_EDIT
```

**ステップ 3 — `app.yaml` の設定**

`MLFLOW_EXPERIMENT_ID` 環境変数のコメントを解除します：

```yaml
- name: MLFLOW_EXPERIMENT_ID
  valueFrom: experiment
```

**ステップ 4 — 再デプロイ**:

```bash
databricks bundle deploy
databricks bundle run databricks_chatbot
```

デプロイ後、「Feedback disabled」バッジが消え、アシスタントメッセージのサムズアップ/ダウンボタンがアクティブになります。

### ローカル開発でのフィードバック有効化

`.env` ファイルにステップ 1 のエクスペリメント ID を `MLFLOW_EXPERIMENT_ID` として設定します：

```bash
MLFLOW_EXPERIMENT_ID=<your-experiment-id>
```

## テスト

このプロジェクトは Playwright をエンドツーエンドテストに使用し、永続モードとエフェメラルモードの両方の動作を検証するデュアルモードテストをサポートしています。

### テストモード

テストは2つの独立したモードで実行され、データベースあり・なし両方の機能が正しく動作することを確認します：

#### データベースありモード

- データベース環境変数を使用（.env で設定済み、または別の場所で宣言済み）
- 完全な Postgres データベースを含む
- チャット履歴の永続化、ページネーション、削除をテスト
- データベースが存在しない場合は警告を表示して停止

#### エフェメラルモード

- データベース接続なし（POSTGRES_URL および PG\* 変数はすべて省略）
- 永続化なしのチャットストリーミングをテスト
- データベースがない場合に UI が適切に動作することを確認

### テストの実行

**すべてのテストを実行（両モード順次実行）**:

```bash
npm test
```

まずデータベースありテスト、次にエフェメラルテストが実行されます。サーバーはモード間で異なる設定で自動的に再起動されます。

**特定のモードで実行**:

```bash
# データベースありモードのみテスト
npm run test:with-db

# エフェメラルモードのみテスト
npm run test:ephemeral
```

### 継続的インテグレーション

GitHub Actions ワークフローは両テストモードを別々のジョブで実行します：

- **test-with-db**: Postgres サービスを含み、マイグレーションを実行し、データベースありテストを実行
- **test-ephemeral**: Postgres なし、マイグレーションなし、エフェメラルテストを実行

両ジョブは CI フィードバックを高速化するために並列実行されます。

## 既知の制限事項

- 画像やその他のマルチモーダル入力には対応していません
- Databricks で最も一般的かつ公式に推奨される認証方法をサポートしています：ローカル開発用の Databricks CLI 認証、およびデプロイ済みアプリ用の Databricks サービスプリンシパル認証。その他の認証メカニズム（PAT、Azure MSI など）は現在サポートされていません。
- アプリのコードがデータベースインスタンス内の固定スキーマ `ai_chatbot` をターゲットにしているため、アプリごとに1つのデータベースを作成します。同一インスタンスで複数のアプリをホストするには：
  - `databricks.yml` 内のデータベースインスタンス名を更新
  - コードベース内の `ai_chatbot` への参照を、既存のデータベースインスタンス内の新しいスキーマ名に更新
  - `npm run db:generate` を実行してデータベースマイグレーションを再生成
  - アプリをデプロイ

## トラブルシューティング

### databricks bundle CLI コマンド実行時の "reference does not exist" エラー

`databricks bundle` コマンドの実行中に以下のようなエラー（または類似の "reference does not exist" エラー）が発生した場合、
Databricks CLI のバージョンが古い可能性があります。
[前提条件](#前提条件)に従って最新バージョンの Databricks CLI をインストールし、再試行してください。

```bash
$ databricks bundle deploy
Error: reference does not exist: ${workspace.current_user.domain_friendly_name}

Name: databricks-chatbot
Target: dev
Workspace:
  User: user@company.com
  Path: /Workspace/Users/user@company.com/.bundle/databricks-chatbot/dev
```

### databricks bundle deploy 時の "Resource not found" エラー

以下のようなエラーは、バンドルの状態がワークスペースにデプロイされたリソースの状態と一致しない場合に、アプリのデプロイ時に発生することがあります：

```bash
$ databricks bundle deploy
Uploading bundle files to /Workspace/Users/user@company.com/.bundle/databricks-chatbot/dev/files...
Deploying resources...
Error: terraform apply: exit status 1

Error: failed to update database_instance

  with databricks_database_instance.chatbot_lakebase,
  on bundle.tf.json line 45, in resource.databricks_database_instance.chatbot_lakebase:
  45:       }

Resource not found


Updating deployment state...
```

これは、バンドル経由でデプロイされたリソースが手動で削除された場合、またはバンドルで指定されたリソースが `databricks bundle` CLI を使用せずに手動で作成された場合に発生します。この種の問題を解決するには、ワークスペース内の実際のデプロイ済みリソースの状態を確認し、`databricks bundle summary` を使用してバンドルの状態と比較してください。不一致がある場合は、[ドキュメント](https://docs.databricks.com/aws/en/dev-tools/bundles/faqs#can-i-port-existing-jobs-pipelines-dashboards-and-other-databricks-objects-into-my-bundle)を参照して、現在のバンドル状態にリソースを手動でバインド（手動作成された場合）またはアンバインド（手動削除された場合）してください。上記の例では、`chatbot_lakebase` データベースインスタンスリソースが `databricks bundle deploy` でデプロイされた後、手動で削除されました。これにより、その後のバンドルのデプロイが失敗しました（バンドルの状態ではリソースが存在するはずですが、ワークスペースには存在しなかったため）。`databricks bundle unbind chatbot_lakebase` を実行してバンドルの状態をインスタンスの削除に合わせて更新し、`databricks bundle deploy` によるその後のバンドルデプロイのブロックを解除しました。

---

**[日本語](#databricks-agent-chat-テンプレート)** | **[English](#databricks-agent-chat-template)**

---

<a href="https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app">
  <h1 align="center">Databricks Agent Chat Template</h1>
</a>

<p align="center">
    A chat application template for interacting with Databricks Agent Serving endpoints, built with ExpressJS, React, Vercel AI SDK, Databricks authentication, and optional Lakebase (database) integration.
</p>

<p align="center">
  <a href="#features"><strong>Features</strong></a> ·
  <a href="#running-locally"><strong>Running Locally</strong></a> ·
  <a href="#deployment"><strong>Deployment</strong></a> ·
  <a href="#optional-chat-ui-features"><strong>Optional Features</strong></a>
</p>
<br/>

This template provides a fully functional chat app for custom code agents and Agent Bricks deployed on Databricks,
but has some [known limitations](#known-limitations) for other use cases. Work is in progress on addressing these limitations.

## Features

- **Databricks Agent and Foundation Model Integration**: Direct connection to Databricks Agent serving endpoints and Agent Bricks
- **Databricks Authentication**: Uses Databricks authentication to identify end users of the chat app and securely manage their conversations.
- **Persistent Chat History (Optional)**: Leverages Databricks Lakebase (Postgres) for storing conversations, with governance and tight lakehouse integration. Can also run in ephemeral mode without database.
- **User Feedback Collection (Optional)**: Thumbs up/down feedback on assistant messages, stored as MLflow assessments on the underlying traces. Requires an MLflow experiment resource to be configured.

## Prerequisites

1. **Databricks serving endpoint**: you need access to a Databricks workspace containing the Agent Bricks or custom agent serving endpoint to chat with.
2. **Set up Databricks authentication**
   - Install the latest version of the [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/install.html). On macOS, do this via:
   ```bash
   brew install databricks
   brew upgrade databricks && databricks -v
   ```
   - Run the following to configure authentication.
     In the snippet below, `DATABRICKS_CONFIG_PROFILE` is the name of the Databricks CLI profile under which to configure
     authentication. If desired, you can update this to a name of your choice, e.g. `dev_workspace`.
   ```bash
     export DATABRICKS_CONFIG_PROFILE='chatbot_template'
     databricks auth login --profile "$DATABRICKS_CONFIG_PROFILE"
   ```

## Deployment

This project includes a [Databricks Asset Bundle (DAB)](https://docs.databricks.com/aws/en/dev-tools/bundles/apps-tutorial) configuration that simplifies deployment by automatically creating and managing all required resources.

1. **Clone the repo**:
   ```bash
   git clone https://github.com/databricks/app-templates
   cd e2e-chatbot-app-next
   ```
2. **Databricks authentication**: Ensure auth is configured as described in [Prerequisites](#prerequisites).
3. **Specify serving endpoint and address TODOs in databricks.yml**: Address the TODOs in `databricks.yml`, setting the default value of `serving_endpoint_name` to the name of the custom code agent or Agent Bricks endpoint to chat with. The optional commented-out sections allow you to enable:
   - **Persistent chat history** — uncomment the two optional `TODO` database blocks to provision and bind a Lakebase database. See [Database Modes](#database-modes) for details. **Tip:** run `./scripts/quickstart.sh` to do this automatically.
   - **User feedback collection** — uncomment the optional `TODO` experiment block and set the experiment ID. Also requires a database (both database `TODO` blocks must be uncommented). See [Feedback Collection](#feedback-collection) for details. **Tip:** run `./scripts/quickstart.sh` to configure both database and feedback automatically.

   - NOTE: if using [Agent Bricks Multi-Agent Supervisor](https://docs.databricks.com/aws/en/generative-ai/agent-bricks/multi-agent-supervisor), you need to additionally grant the app service principal the `CAN_QUERY` permission on the underlying agent(s) that the MAS orchestrates. You can do this by adding those
     agent serving endpoints as resources in `databricks.yml` (see the NOTE in `databricks.yml` on this)
4. **Validate the bundle configuration**:

   ```bash
   databricks bundle validate
   ```

5. **Deploy the bundle**. The first deployment may take several minutes for provisioning resources (especially if database is enabled), but subsequent deployments are fast:

   ```bash
   databricks bundle deploy
   ```

   This creates:

   - **App resource** ready to start
   - **Lakebase database instance** (only if database resource is uncommented)

6. **Start the app**:

   ```bash
   databricks bundle run databricks_chatbot
   ```

7. **View deployment summary** (useful for debugging deployment issues):
   ```bash
   databricks bundle summary
   ```

### Deployment Targets

The bundle supports multiple environments:

- **dev** (default): Development environment
- **staging**: Staging environment for testing
- **prod**: Production environment

To deploy to a specific target:

```bash
databricks bundle deploy -t staging --var serving_endpoint_name="your-endpoint"
```

## Running Locally

### Quick Start (Recommended)

Use our automated quickstart script for the fastest setup experience:

1. **Clone the repository**:

   ```bash
   git clone https://github.com/databricks/app-templates
   cd e2e-chatbot-app-next
   ```

2. **Run the quickstart script**:

   ```bash
   ./scripts/quickstart.sh
   ```

   The quickstart script will:
   - **Install prerequisites** - Automatically installs jq, nvm, Node.js 20, and Databricks CLI
   - **Configure authentication** - Helps you select or create a Databricks CLI profile
   - **Set up serving endpoint** - Prompts for your endpoint name and validates it exists
   - **Database setup (optional)** - Choose persistent chat history or ephemeral mode
   - **Deploy to Databricks (optional)** - Optionally deploys resources and provisions database
   - **Configure local environment** - Automatically creates and populates .env
   - **Run migrations** - Sets up database schema if database is enabled

   The script handles the entire setup process automatically, including waiting for database provisioning and configuring connection details.

3. **Start the application**:

   Use the convenience script:
   ```bash
   ./scripts/start-app.sh
   ```

   Or manually:
   ```bash
   npm install  # Install/update dependencies
   npm run dev  # Start development server
   ```

   The app starts on [localhost:3000](http://localhost:3000) (frontend) and [localhost:3001](http://localhost:3001) (backend)

   **Tip:** The `start-app.sh` script is useful for quickly starting the app after initial setup, as it ensures dependencies are up-to-date before starting the dev server.

### Manual Setup (Alternative)

If you prefer to configure the environment manually:

1. **Clone and install**:

   ```bash
   git clone https://github.com/databricks/app-templates
   cd e2e-chatbot-app-next
   npm install
   ```

2. **Set up environment variables**:

   ```bash
   cp .env.example .env
   ```

   Address the TODOs in `.env`, specifying your Databricks CLI profile and database connection details.

3. **Run the application**:

   ```bash
   npm run dev
   ```

   The app starts on [localhost:3000](http://localhost:3000)

### Optional Chat UI Features

The chat UI supports two optional features that can be enabled by updating `databricks.yml`:

### User Feedback

Users can give thumbs up/down on assistant responses. Feedback is stored as [MLflow assessments](https://docs.databricks.com/aws/en/generative-ai/agent-evaluation/assessments) on the underlying traces, making it easy to review and act on in the MLflow Experiment Tracking UI.

Feedback is **disabled by default**. See [Feedback Collection](#feedback-collection) for setup instructions.

> **Note:** If you're using one of the conversational agent templates (e.g. `agent-openai-agents-sdk`, `agent-langgraph`), their `databricks.yml` already creates and binds an MLflow experiment — feedback works automatically after `databricks bundle deploy`, with no extra configuration required.

### Persistent Chat History

By default, conversation messages are stored in memory and lost when the server restarts. To persist chat history across sessions, bind a Lakebase database in `databricks.yml`.

See [Database Modes](#database-modes) for setup instructions.

---

## Database Modes

The application supports two operating modes:

#### Persistent Mode (with Database)

This is the default mode when database environment variables are configured. In this mode:

- Chat conversations are saved to Postgres/Lakebase
- Users can access their chat history via the sidebar
- Conversations persist across sessions
- A database connection is required (POSTGRES_URL or PGDATABASE env vars)

#### Ephemeral Mode (without Database)

The application can also run without a database. In this mode:

- Chat conversations work normally but are **not saved**
- The sidebar shows "No chat history available"
- A small "Ephemeral" indicator appears in the header
- Users can still have conversations with the AI, but history is lost on page refresh

#### Selecting a Database Mode

The application will default to "Ephemeral mode" when no database environment variables are set.
To run in persistent mode, ensure your environment contains the following database variables:

```bash
# Useful for local development
POSTGRES_URL=...

# OR

# Handled for you when using Databricks Apps
PGUSER=...
PGPASSWORD=...
PGDATABASE=...
PGHOST=...
```

The app will detect the absence or precense of database configuration and automatically run in the correct mode.

#### Enabling Database After Installation

If you initially installed the template without database support (ephemeral mode) and want to add persistent chat history later, you can re-run the quickstart script:

```bash
./scripts/quickstart.sh
```

When prompted about enabling persistent chat history, select "Yes". The script will:
- Uncomment the required database sections in `databricks.yml`
- Optionally deploy the Lakebase database instance
- Configure your `.env` file with database connection details
- Run database migrations if the database is provisioned
- Set up your local environment with the correct database settings

The script handles all configuration automatically, including:
- Detecting your Databricks workspace and authentication
- Calculating the correct database instance name for your target environment
- Retrieving the database host (PGHOST) after provisioning
- Updating environment variables with the correct values

**Manual Steps (Alternative):**

If you prefer to enable the database manually:

1. **Edit `databricks.yml`** - Uncomment both database sections:
   - Database instance resource (`chatbot_lakebase`) around line 18
   - Database resource binding (`- name: database`) around line 41

2. **Deploy the database**:
   ```bash
   databricks bundle deploy
   ```
   (First deployment takes several minutes for provisioning)

3. **Configure `.env`** with database variables:
   ```bash
   PGUSER=your-databricks-username
   PGHOST=your-postgres-host  # Get with: ./scripts/get-pghost.sh
   PGDATABASE=databricks_postgres
   PGPORT=5432
   ```

4. **Run database migrations**:
   ```bash
   npm run db:migrate
   ```

## Feedback Collection

The chat app supports optional thumbs up/down feedback on assistant messages. When enabled, feedback is stored as [MLflow assessments](https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app) on the traces emitted by your agent endpoint, making it easy to review and act on in the MLflow UI.

Feedback is **disabled by default**. A "Feedback disabled" badge appears in the header when it is not configured.

> **Note:** Feedback vote persistence (restoring thumbs up/down state on page reload) requires a database. Both features can be enabled together in one step using the quickstart script.

### Recommended: use the quickstart script

The easiest way to enable feedback (and persistent chat history) is to run the interactive setup script:

```bash
./scripts/quickstart.sh
```

The script automatically:
1. Looks up the MLflow experiment ID linked to your serving endpoint
2. Uncomments and configures the feedback `TODO` block in `databricks.yml` (setting `experiment_id`) and the `MLFLOW_EXPERIMENT_ID` env var in `app.yaml`
3. Uncomments both database `TODO` blocks in `databricks.yml` to provision and bind a Lakebase database

After the script completes, run `databricks bundle deploy` to apply the changes.

### Manual setup

If you prefer to configure manually:

**Step 1 — Find your experiment ID**

```bash
# For a custom-code agent or Agent Bricks serving endpoint
npx tsx scripts/get-experiment-id.ts --endpoint <your-endpoint-name>

# For an Agent Bricks Knowledge Assistant or Multi-Agent Supervisor
npx tsx scripts/get-experiment-id.ts --agent-brick <agent-brick-name>
```

**Step 2 — Configure `databricks.yml`**

Uncomment both database `TODO` blocks (required for vote persistence) and the feedback `TODO` block, setting the experiment ID from Step 1:

```yaml
- name: experiment
  description: "MLflow experiment for collecting user feedback"
  experiment:
    experiment_id: "your-experiment-id"
    permission: CAN_EDIT
```

**Step 3 — Configure `app.yaml`**

Uncomment the `MLFLOW_EXPERIMENT_ID` environment variable:

```yaml
- name: MLFLOW_EXPERIMENT_ID
  valueFrom: experiment
```

**Step 4 — Redeploy**:

```bash
databricks bundle deploy
databricks bundle run databricks_chatbot
```

Once deployed, the "Feedback disabled" badge disappears and the thumbs up/down buttons become active on assistant messages.

### Enabling feedback for local development

Set `MLFLOW_EXPERIMENT_ID` in your `.env` file to the experiment ID from Step 1:

```bash
MLFLOW_EXPERIMENT_ID=<your-experiment-id>
```

## Testing

The project uses Playwright for end-to-end testing and supports dual-mode testing to verify behavior in both persistent and ephemeral modes.

### Test Modes

Tests run in two separate modes to ensure both database and non-database functionality work correctly:

#### With Database Mode

- Uses database environment variables (either set in .env or declared elsewhere)
- Includes full Postgres database
- Tests chat history persistence, pagination, and deletion
- Will throw a warning and stop if no database exists

#### Ephemeral Mode

- No database connection (all POSTGRES_URL and PG\* variables omitted)
- Tests chat streaming without persistence
- Ensures UI gracefully handles missing database

### Running Tests

**Run all tests (both modes sequentially)**:

```bash
npm test
```

This runs with-db tests first, then ephemeral tests. The server automatically restarts between modes with different configurations.

**Run specific mode**:

```bash
# Test with database only
npm run test:with-db

# Test ephemeral mode only
npm run test:ephemeral
```

### Continuous Integration

The GitHub Actions workflow runs both test modes in separate jobs:

- **test-with-db**: Includes Postgres service, runs migrations, executes with-db tests
- **test-ephemeral**: No Postgres, no migrations, executes ephemeral tests

Both jobs run in parallel for faster CI feedback.

## Known limitations

- No support for image or other multi-modal inputs
- The most common and officially recommended authentication methods for Databricks are supported: Databricks CLI auth for local development, and Databricks service principal auth for deployed apps. Other authentication mechanisms (PAT, Azure MSI, etc) are not currently supported.
- We create one database per app, because the app code targets a fixed `ai_chatbot` schema within the database instance. To host multiple apps out of the same instance, you can:
  - Update the database instance name in `databricks.yml`
  - Update references to `ai_chatbot` in the codebase to your new desired schema name within the existing database instance
  - Run `npm run db:generate` to regenerate database migrations
  - Deploy your app

## Troubleshooting

### "reference does not exist" errors when running databricks bundle CLI commands

If you get an error like the following (or other similar "reference does not exist" errors)
while running `databricks bundle` commands, your Databricks CLI version may be out of date.
Make sure to install the latest version of the Databricks CLI (per [Prerequisites](#prerequisites)) and try again.

```bash
$ databricks bundle deploy
Error: reference does not exist: ${workspace.current_user.domain_friendly_name}

Name: databricks-chatbot
Target: dev
Workspace:
  User: user@company.com
  Path: /Workspace/Users/user@company.com/.bundle/databricks-chatbot/dev
```

### "Resource not found" errors during databricks bundle deploy

Errors like the following one can occur when attempting to deploy the app if the state of your bundle does not match the state of resources
deployed in your workspace:

```bash
$ databricks bundle deploy
Uploading bundle files to /Workspace/Users/user@company.com/.bundle/databricks-chatbot/dev/files...
Deploying resources...
Error: terraform apply: exit status 1

Error: failed to update database_instance

  with databricks_database_instance.chatbot_lakebase,
  on bundle.tf.json line 45, in resource.databricks_database_instance.chatbot_lakebase:
  45:       }

Resource not found


Updating deployment state...
```

This can happen if resources deployed via your bundle were then manually deleted, or resources specified by your bundle
were manually created without using the `databricks bundle` CLI. To resolve this class of issue, inspect the state of the actual deployed resources
in your workspace and compare it to the bundle state using `databricks bundle summary`. If there is a mismatch,
[see docs](https://docs.databricks.com/aws/en/dev-tools/bundles/faqs#can-i-port-existing-jobs-pipelines-dashboards-and-other-databricks-objects-into-my-bundle) on how to
manually bind (if resources were manually created) or unbind (if resources were manually deleted) resources
from your current bundle state. In the above example, the `chatbot_lakebase` database instance resource
was deployed via `databricks bundle deploy`, and then manually deleted. This broke subsequent deployments of the bundle
(because bundle state indicated the resource should exist, but it did not in the workspace). Running `databricks bundle unbind chatbot_lakebase` updated bundle state to reflect the deletion of the instance,
unblocking subsequent deployment of the bundle via `databricks bundle deploy`.
