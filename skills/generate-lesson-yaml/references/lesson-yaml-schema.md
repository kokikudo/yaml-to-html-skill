# lesson.yaml — ハンズオン教材の骨格

`lesson.yaml` は**到達物・前提・手順・検証点**を記録する。

## メンタルモデル

```
lesson.yaml = 何を作るか（project）
            + どこまでやるか（scope）
            + どういう順で（steps）
            + 各手順の根拠はどれか（source_refs → evidence.yaml）
```

`lesson.yaml` 単体では中身が正しいかを判断できない。判断材料は `evidence.yaml` 側にあり、
2 つのファイルは `source_refs` / `needs_facts` の id でのみ繋がる。

## Do / Don't

- ✅ 事実を主張するすべての項目に `origin` を付ける。
- ✅ 埋まらない事実があるときは**末尾から切る**。途中の手順は抜かない。
- ❌ ビルドやテストが通ることを保証する記述を書かない。それはドキュメントの責務。
- ❌ 特定のビルドツール・エディタ・拡張機能を前提にした手順を書かない。
- ❌ `origin: authored` を黙って使わない。`origin_note` に何を埋めたかを必ず残す。
- ❌ 他のフィールドから導ける値をフィールドとして持たない。

## origin — このスキーマの中心

`origin` は添え物ではない。コード・要件・検証点のそれぞれが個別に持つ。値ごとに、要求される
`source_refs` の件数と `origin_note` の有無が違う。**この規則は機械的に検算できる。**

| `origin` | `source_refs` | `origin_note` | 意味 |
|---|---|---|---|
| `verbatim_from_doc` | 1 件以上 | 不要 | ドキュメントの記述をそのまま使った |
| `adapted` | 1 件以上 | **必須** | 公式の記述を、この教材の型名・構成に合わせて書き換えた |
| `synthesized` | **2 件以上** | **必須** | 複数ページの記述を統合した |
| `authored` | **0 件（空）** | **必須** | ドキュメントが黙っている部分を埋めた |

`authored` は**減らすべき値**。付いている箇所はスキルが自分の一般知識で書いた箇所であり、
検証手段がない。0 件にはならない（プロジェクト作成手順はどのドキュメントもまず書いていない）が、
比率は毎回報告する。

**`origin` を付ける対象**は「学習者がそのまま手を動かす対象」と「事実を主張する箇所」——
`project.scaffold` / `project.requirements[]` / `steps[].files[]` / `steps[].checkpoint` /
`steps[].common_errors[]`。
`steps[].title` や `steps[].why` は教材側の語りなので付けない

## needs_facts と source_refs — 2 パスの役割分担

両方とも `evidence.yaml` の fact id を指すが、**書かれる時期が違う**。

- `steps[].needs_facts` — 「この手順を書くには何を知る必要があるか」。
  取得より前に書かれ、そのまま取得指示になる。取得後も残す（何を要求したかの記録）。
- `<item>.source_refs` —「この 1 項目は実際にどの fact に基づくか」。
  1 手順が 3 つの事実を 2 つのファイルに配分するとき、どちらがどれに拠ったかはここにしかない。

## スキーマ（`version: lesson/v1`）

*optional* と書いていないフィールドは必須。

```yaml
version: lesson/v1

goal:
  title: string      # 教材のタイトル
  outcome: string    # 終えたときに何ができているか、1 文
  request: string    # 元になったユーザーの要求、逐語。再生成の唯一の入力なので必ず残す

project:
  name: string       # プロジェクト名
  stack: string      # 自由記述。例 "Swift / SwiftUI"。
  scaffold:
    origin: authored           # 実質常に authored
    origin_note: string
    steps:                     # 粗く書く。手順を書き込むほど壊れやすくなる
      - string
  requirements:                # optional — 前提。availability など
    - text: string
      origin: <origin>
      origin_note: string      # origin の規則に従う
      source_refs: [fact_id]

scope:
  covers:                      # この教材が扱う範囲
    - string
  excludes:                    # optional — 意図的に外した範囲
    - string
  truncated: bool              # 末尾を切ったか
  truncated_reason: string     # truncated: true のとき必須。何が書けなくて止めたか
  unmet_facts:                 # truncated: true のとき必須。埋まらなかった事実の一行説明
    - string

steps:
  - id: string                 # 安定した kebab / snake の id
    title: string
    why: string                # なぜこの手順が要るか。教材側の語り。origin は付けない
    needs_facts: [fact_id]     # このステップに必要なファクトの宣言
    files:
      - path: string           # プロジェクト内の相対パス
        action: create | update
        lang: string           # optional — シンタックスハイライト用
        origin: <origin>
        origin_note: string
        source_refs: [fact_id]
        content: |             # その時点のファイル全文。差分ではない
          …
    checkpoint:
      kind: build | run | observe
      expect: string           # ここまでで何が確認できるか。できないことも書く
      origin: <origin>
      origin_note: string
      source_refs: [fact_id]
    common_errors:             # optional — ドキュメントに記載のあるものだけ
      - symptom: string
        cause: string
        source_ref: fact_id    # 必須。これがあるので推測を書けない
```

## フィールド注記

- **`goal.request` は逐語で残す。** 教材を作り直す・広げるときの唯一の入力。要約すると、
  何が求められていたかが二度と復元できない。

- **`goal` に `audience` は置かない。** 読み手・密度・トーンは `view.yaml`（`view/v1`）の
  担当で、両方に書くと必ず食い違う。`lesson.yaml` は「何を作るか」だけを持つ。

- **`project.name` は教材が決める。** ゼロから作る前提なので初期状態を完全に固定できる。
  検証点が「`PhotoEntity` が定義できている」と言うためには、それが置かれる場所も教材側が
  決まっていないといけない。

- **`project.stack` はソース非依存に。** 言語とフレームワーク名程度に留める。特定の IDE や
  ビルドコマンドを書き込むと、そこが導入障壁になる。

- **`scope.truncated` は失敗の記録ではない。** ドキュメントが書いていない範囲まで教材が
  伸びなかったという事実であり、正しい振る舞い。`unmet_facts` は fact id ではなく**一行の
  説明**にする — 切られた手順は `lesson.yaml` から消えているので、id だけ残っても読み手には
  何も伝わらない。

- **`checkpoint.expect` には「まだできないこと」も書く。** 「型は定義できている。まだ検索には
  出ない」のような書き方。ここを省くと、学習者は途中の手順で動かないことを不具合と誤認する。

- **`checkpoint.kind: observe` は人間にしか実行できない。** 「Spotlight の検索結果に出る」の
  ような確認を機械検証できるふりをしない。`source_refs` でその確認の根拠を示し、判断は学習者に
  委ねる。元ページのパスは出典側のエントリに載る。

- **`common_errors[].source_ref` が必須なのは意図的。** 教材は実行して確かめる手段を持たない
  ので、記載のない「よくある詰まり」は推測になる。スキーマがそれを書けなくしている。

## URL について（オフライン安全性）

すべての `path` から `http(s)://` を落とす。この値は下流でオフライン自己完結 HTML に入り、
内部のスクリプトで URL スキームを弾く。ここで習慣づけておくと 2 段先で落ちない。

## 最小例

```yaml
version: lesson/v1

goal:
  title: "App Intents で写真を Spotlight に載せる"
  outcome: "自作の写真エンティティが Spotlight の検索結果に出るところまで"
  request: "App Intents を使って自分のアプリのデータを Spotlight に出したい"

project:
  name: "SpotlightPhotos"
  stack: "Swift / SwiftUI"
  scaffold:
    origin: authored
    origin_note: "プロジェクト作成手順はドキュメントに記載がないため補った"
    steps:
      - "新規の iOS App プロジェクトを SpotlightPhotos の名前で作成する"
  requirements:
    - text: "iOS 16.0 以上"
      origin: verbatim_from_doc
      source_refs: [f-availability]

scope:
  covers:
    - "App entity の定義"
    - "Spotlight への index 登録"
  excludes:
    - "App Shortcuts / Siri 連携"
  truncated: false

steps:
  - id: st-entity
    title: "PhotoEntity を定義する"
    why: "Spotlight のインデックス対象は entity なので、まず写真を entity として表す"
    needs_facts: [f-appentity-conformance]
    files:
      - path: "PhotoEntity.swift"
        action: create
        lang: swift
        origin: adapted
        origin_note: "公式の宣言例を、この教材の型名 PhotoEntity に合わせて書き換えた"
        source_refs: [f-appentity-conformance]
        content: |
          …
    checkpoint:
      kind: build
      expect: "型が定義できている。まだ検索には出ない"
      origin: authored
      origin_note: "この段階で何が確認できるかはドキュメントに記載がないため補った"
```

この例が参照している 2 つの fact（`f-appentity-conformance` / `f-availability`）は
`evidence-yaml-schema.md` の最小例にそのまま入っている。2 ファイルはこの id だけで繋がる。

（`content` を省略しているのは紙面の都合。実物では省略しない。）
