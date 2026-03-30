**[English はこちら](#build-production-scale-governed-ai-agent-in-databricks)** | **[日本語](#databricks-で本番運用レベルの-ai-エージェントを構築する)**

---

# Databricks で本番運用レベルの AI エージェントを構築する

> **ローカル環境だけで動くおもちゃのデモではなく、本番環境で通用する AI アプリケーションを構築するための実践ガイドです。** Databricks 上でガバナンスの効いたプロダクションレディな AI エージェントを、ゼロからデプロイまで一気通貫で学びます。

このワークショップシリーズでは、**本番運用**を最終ゴールに据え、評価・ガバナンス・ヒューマンインザループによるフィードバック・モニタリングといった要素を初日から組み込んで開発を進めます。

3つのレベル。ミッションは1つ：**Databricks 上で、より賢く実用的な AI エージェントを設計・構築できるようになること。**

## 自分に合ったレベルを選ぶ

| レベル | こんな方に | ゴール |
|--------|-----------|--------|
| **Simple（入門）** | 「自社の業務に特化したエージェントを作りたい」 | Databricks のマネージドサービスを活用し、ガバナンスの効いたエージェントをエンタープライズ規模でデプロイできる |
| **Medium（中級）** | 「メモリを持つカスタムエージェントを構築したい」 | マネージドとカスタムコンポーネントを組み合わせたエージェンティックシステムを設計できる |
| **[Advanced（上級）](./advanced/)** | 「フルカスタムで高度なエージェンティックメモリアプリを作りたい」 | LangGraph・MCP ツール・Lakebase による永続メモリを活用した本番品質の AI を構築できる |

今の自分に合ったレベルを選んでください。各レベルは完結しているので、クローンしたらすぐに始められます。

## エージェントのライフサイクル（実際に学ぶこと）

すべてのレベルで、同じエンドツーエンドのライフサイクルに沿って進めます。レベルが上がるほど内容は深くなりますが、基本の設計図は共通です：

```
  エンタープライズ AI のための LLM 活用
        |
  エージェント構築  ------>  評価とイテレーション
        |                       |
  ヒューマンインザループ  <----------+
        |
  ガバナンスとモニタリング
        |
  AgentOps（開発 --> 本番）
```

「API を呼んであとは祈る」だけでは終わりません。**テスト済み・ガバナンス付き・可観測・継続改善**のエージェントを構築する方法を学びます。

## クイックスタート

```bash
git clone https://github.com/AnanyaDBJ/databricks-ai-workshops.git
cd databricks-ai-workshops
```

```
simple/        # Databricks AI が初めての方はここから
medium/        # マネージドサービスの先へ進みたい方向け
advanced/      # フルカスタム構成。補助輪なし
```

> **コーディングエージェント対応** — 各レベルには Claude Code 用のスキルファイルとコンテキストファイルが同梱されています。ただし、Vibe コーディングだけで済ませないでください。まずコンセプトを理解し、*その上で*構築しましょう。作るエージェントの品質は、仕組みへの理解度に比例します。

## このワークショップが存在する理由

「Hello World」レベルのエージェントデモは世の中にあふれています。本当に足りないのは、**難しいところ**——評価・ガバナンス・モニタリング・そしてプロトタイプをプロダクトに昇華させる運用の規律です。

どのレベルを修了しても、Databricks 上でエージェントをアイデアから本番運用まで持っていく方法が身につきます。ここで学ぶパターンはフレームワーク非依存で将来にわたって有効です——ツールは変わっても、基礎は変わりません。

**ありふれたエージェントと優れたエージェントの違いは、アーキテクチャにあります。さあ、構築を始めましょう。**

---

**[日本語はこちら](#databricks-で本番運用レベルの-ai-エージェントを構築する)** | **[English](#build-production-scale-governed-ai-agent-in-databricks)**

---

# Build Production Scale Governed AI Agent in Databricks

> ** A practical guide to build Production-ready AI application and not toy demos that work well on your computer.** Start building governed, production-ready AI agents on Databricks, from zero to deployed, with everything in between.

This workshop series takes you all the way to **production** — with evaluation, governance, human-in-the-loop feedback, and monitoring baked in from day one.

Three levels. One mission: **make you define smareter and practical AI agents ( On Databricks). **

## Choose Your Path

| Level | You'll Go From... | ...To |
|-------|-------------------|-------|
| **Simple** | "How to build a bespoke agent for my business application.?" | Deploying governed agents with Databricks managed services at enterprise scale |
| **Medium** | "I want to build a customised agent with memory ?" | Architecting agentic systems that mix managed + custom components |
| **[Advanced](./advanced/)** | "I want full control and create an advanced agentic memory application." | Production-grade AI with LangGraph, MCP tools, and persistent memory via Lakebase |

Pick the level that matches where you are. Each one is fully self-contained — just clone and go.

## The Agent Lifecycle (What You'll Actually Learn)

Every level follows the same end-to-end lifecycle. The depth increases, but the blueprint stays the same:

```
  LLMs for Enterprise AI
        |
  Build Agents  ------>  Evaluate & Iterate
        |                       |
  Human-in-the-Loop  <----------+
        |
  Governance & Monitoring
        |
  AgentOps (Dev --> Production)
```

This isn't just "call an API and hope for the best." You'll learn to build agents that are **tested, governed, observable, and continuously improving.**

## Quick Start

```bash
git clone https://github.com/AnanyaDBJ/databricks-ai-workshops.git
cd databricks-ai-workshops
```

```
simple/        # New to Databricks AI? Start here.
medium/        # Ready to go beyond managed services.
advanced/      # Full custom stack. No training wheels.
```

> **Coding agent friendly** — every level ships with Claude Code skills and context files. But don't just vibe-code your way through it. Learn the concepts, *then* build. The agents you create are only as good as your understanding of what's under the hood.

## Why This Exists

There are plenty of "hello world" agent demos out there. What's missing is the **hard part** — evaluation, governance, monitoring, and the operational rigor that separates a prototype from a product.

By the end of any level, you'll know how to take an agent from idea to production on Databricks. These patterns are framework-agnostic and future-proof — the tools may change, but the fundamentals won't.

**The difference between a basic agent and an extraordinary one is how you architect it. Let's build.**
