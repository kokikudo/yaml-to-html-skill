# evidence.yaml — 教材の出典

`evidence.yaml` は、教材を書くために実際に取得したドキュメントの記述を**逐語で**記録する。
`lesson.yaml` が「何を作るか」なら、こちらは「なぜそう書けるのか」。

## メンタルモデル

```
lesson.yaml の needs_facts / source_refs
        ↓ id で参照
evidence.yaml の facts[]   ← 取得したページの記述、そのまま
```

粒度は**ページではなく事実**。1 ページから 3 つの事実を取ることもあれば、1 つも取らないことも
ある。ページ単位で持つと「取ったが使わない記述」が混ざり、それは索引先行 + 遅延取得という
この設計が避けたかったものそのものになる。

**ここだけは要約しない。** コードと宣言を言い換えた時点で、教材がドキュメントから生成された
ものである意味が消える。`abstract` を粗く持つ索引とは、精度の配分が正反対になっている。

## Do / Don't

- ✅ `verbatim` はソースの文字列をそのまま入れる。整形も言い換えもしない。
- ✅ 1 fact = 1 主張。長い節を丸ごと 1 fact に詰めない。
- ✅ どこから取ったかを `path` と `fetched_at` で必ず残す。
- ❌ 取得していない内容を fact として書かない。それは fact ではなく `lesson.yaml` 側の
  `origin: authored`。
- ❌ `lesson.yaml` のどこからも参照されない fact を残さない（見つけたら削除する）。
- ❌ 自分の解説をここに混ぜない。解説は `lesson.yaml` の `why` か `origin_note` の担当。

## スキーマ（`version: evidence/v1`）

*optional* と書いていないフィールドは必須。

```yaml
version: evidence/v1

facts:
  - id: string          # lesson.yaml の needs_facts / source_refs が指す id
    kind: concept | declaration | code_example | constraint | procedure
    title: string       # この事実が何かの 1 行。needs_facts の宣言を読めるようにするため
    source:
      page_title: string   # 取得したページの自身のタイトル
      path: string         # scheme を落とした実パス。索引か親ページから転記する
      fetched_at: string   # ISO 日付。この記述をいつ見たか
    lang: string        # optional — kind: code_example のとき、ハイライト用
    verbatim: |         # 逐語。ここが本体
      …
```

これで全部。

## フィールド注記

- **`kind` の 5 値。** 教材のどこに置ける事実かを示す。
  - `concept` — 概念の説明文。手順の `why` の根拠になる。
  - `declaration` — API の宣言、準拠要件、シグネチャ。
  - `code_example` — ドキュメントに載っているコード。
  - `constraint` — 前提・制限・プラットフォーム可用性。`requirements` の根拠。
  - `procedure` — ドキュメントが明示している操作手順。

- **`id` は `lesson.yaml` が先に決める。** パス①で `needs_facts` に書いた id を、パス②で
  そのまま採用する。取得後に付け替えると宣言と束縛が繋がらなくなる。

- **`title` は `verbatim` から導けない。** `verbatim` が 10 行のコードのとき、それが何の例
  なのかは本文中に書かれていない。`needs_facts: [f-appentity-conformance]` という宣言だけを
  見た読み手が意味を取れるようにするための 1 行。

- **`source.path` は転記する。組み立てない。** 索引の `path` か、親ページのデータが持つ URL を
  そのまま使う。タイトルからスラグを推測すると 404 を踏む（Apple の「Spotlight integration」
  は `…/appintents/spotlight` にある）。`http(s)://` は落とす。

- **`source.fetched_at` はこの fact の鮮度そのもの。** ドキュメントは年次で入れ替わる。
  教材が古いかどうかを判断する材料は、索引の世代番号のような間接的な値ではなく、ここにある。
  だから `lesson.yaml` は索引と紐づけない。

- **`used_by_steps` は置かない。** `lesson.yaml` の `source_refs` から機械的に導ける。
  代わりに、生成の最後に「全 fact が参照されているか」を検算する手順をスキル側に置いてある
  （導ける値をフィールドとして持つと、更新漏れで嘘をつく）。

- **`page_id` は置かない。** 索引に載っていないページを一時的に辿ることがあり、そのページには
  索引上の id がない。`path` と `page_title` で十分に特定できる。

## 最小例

```yaml
version: evidence/v1

facts:
  - id: f-appentity-conformance
    kind: concept
    title: "App entity がシステムに何を提供するか"
    source:
      page_title: "App entities"
      path: "developer.apple.com/documentation/appintents/app-entities"
      fetched_at: "2026-08-12"
    verbatim: |
      App entities provide the system with information about your app's data,
      or about concepts related to your app's data.

  - id: f-availability
    kind: constraint
    title: "App Intents のプラットフォーム可用性"
    source:
      page_title: "App Intents"
      path: "developer.apple.com/documentation/appintents"
      fetched_at: "2026-08-12"
    verbatim: |
      iOS 16.0+ | iPadOS 16.0+ | Mac Catalyst 16.0+ | macOS 13.0+
      tvOS 16.0+ | visionOS 1.0+ | watchOS 9.0+
```
