# テンプレートの契約

HTML の**唯一の出所**は `templates/` の 2 ファイル。`build_lesson_html.py` は
`__TOKEN__` を置換するだけで、外枠・CSS・JS を組み立てない。

```
templates/main.html     レッスン一覧
templates/lesson.html   レッスン 1 本のページ
```

## 編集のルール

- **レイアウトを変えるときはテンプレートを直す。** 生成された `<bundle>/main.html` や
  `lessons/*/*.html` を手で直しても、次のビルドで消える。
- **テンプレート先頭の `<!-- … -->` は差し込み口の説明。** ビルド時に取り除かれる
  （そこに書かれた `__TOKEN__` まで置換されないようにするため）。
- **`__TOKEN__` を増やすときは、テンプレートとスクリプトの両方を同時に直す。** 置換され
  なかったトークンは生成物にそのまま残るので、「生成物に `__` が残っていないこと」で検査できる。
- **外部リソースを足さない。** `<link rel="stylesheet">` / `<script src>` / 外部フォント /
  リモート画像は `validate_html.py` が落とす。CSS も JS もインラインのまま。

## `templates/main.html` の差し込み口

| トークン | 中身 | 元データ |
|---|---|---|
| `__TITLE__` | ページ見出し | バンドル直下 `narration.json` の `title` |
| `__OVERVIEW_BODY__` | 概要本文 + 補足 | バンドル直下 `narration.json` の `lead` / `notes` |
| `__OVERVIEW_META__` | 対応環境のチップ列 | バンドル直下 `narration.json` の `availability` |
| `__SOURCE_NOTE__` | 出典表記 | バンドル直下 `narration.json` の `source_note` |
| `__LESSON_CARDS__` | レッスンカード | `lessons.json` + 各レッスンの `narration.json` の `summary` |

`__LESSON_CARDS__` 以外はすべてバンドル直下の `narration.json` 由来。`index.yaml` を読んで
`title` / `lead` / `availability` を書くのは narration を書く工程であって、ビルドは索引を
読まない（→ `bundle-structure.md`）。

## `templates/lesson.html` の差し込み口

| トークン | 中身 | 元データ |
|---|---|---|
| `__LESSON_TITLE__` | ヘッダーのレッスン名 | `goal.title` |
| `__BACK_HREF__` | 戻り先 | 固定 `../../main.html` |
| `__STEP_COUNT__` | 「全 N 手順」 | `steps` の数 |
| `__NAV_ITEMS__` | 左ペインの `<li><button class="nav-btn">` 群 | 概要 + 各 Step + 出典一覧 |
| `__PANELS__` | 右ペインの `<article class="panel">` 群 | 同上（ナビと同じ順・同じ数） |

**ナビとパネルは同数・同順でなければならない。** JS は index で対応付ける。

## 画面に出るもの / 出ないもの

**`lesson.yaml` / `evidence.yaml` から出るのは、事実そのもの**（タイトル・パス・コード・
前提・確認の種別・出典）。**受講者が読む文章は narration JSON から出る**
（→ `narration-contract.md`）。

| 画面の場所 | 事実（YAML） | 文章（narration） |
|---|---|---|
| レッスンカード | `goal.title` / 手順数 / `stack` | `summary` |
| 概要ページ | 手順数・`stack`・前提・下ごしらえ・扱う範囲 | `lead` / `goal` / `notes` / 各リストの書き直し |
| Step ページ | `title` / ファイルパス / `action` / `lang` / コード全文 / `checkpoint.kind` | `lead` / `files.<path>` / `notes` / `checkpoint` |
| つまずき | `common_errors[].symptom` / `cause` | （YAML のまま。記載のあるものだけなので） |
| 出典一覧 | fact の `title` / `path` / `verbatim` / `kind` / 使う場面 | `evidence.facts.<id>`（日本語要旨） |

**画面に出さないもの:**

- `origin` / `origin_note` — 作り手のための追跡情報。ビルド時に規則を**検査**し、違反を
  警告として出すだけ。バッジも内訳も UI には出さない。
- `needs_facts` — 取得の記録。
- fact の id — 出典一覧の末尾に薄く出すだけ（リンクの実体は `href="#fact=<id>"`）。
- `goal.request` — ユーザーの元の要求。受講者には関係がない。
- YAML / JSON のファイル名、バンドル内のパス。

## 出典への導線

- 出典は**根拠になっている当のものの直下**に出す。まとめない。`source_refs` は
  **タイトルのリンク**にして並べる（fact id は出さない）。

  | YAML | 出す場所 | ラベル |
  |---|---|---|
  | `files[].source_refs` | そのコードブロックの直下（`.file` の中） | このコードの出典 |
  | `checkpoint.source_refs` | 「ここまでの確認」の枠の中 | この確認の出典 |
  | `common_errors[].source_ref` | そのつまずき 1 件の中 | 出典 |
  | `requirements[].source_refs` | その前提 1 項目の中 | 出典 |

- リンクは同じページ内の出典一覧パネルへ飛び、該当エントリまでスクロールして一瞬強調する
  （`#fact=<id>`）。ページ外への遷移は起きない。
- **ドキュメントのパスが画面に出るのは、引用した出典としてだけ。**
- 出典一覧の 1 エントリの並び順は **タイトル → パス（URL） → 日本語要旨 → 原文 →
  メタ情報（ページ名・取得日・使う場面・fact id）**。目立たせる順序をこの通りに保つ。

## 文章の描画

- `narration` の文字列は**空行で段落に分割**され、`` `…` `` は `<code>` になる。
- それ以外の記法（見出し、リスト、リンク）は解釈しない。構造が要るなら、テンプレートと
  レンダラの側に項目を足す。
