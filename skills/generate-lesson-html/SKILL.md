---
name: generate-lesson-html
description: lesson.yaml と evidence.yaml（generate-lesson-yaml の出力）から、オフラインで完結するハンズオン教材の HTML バンドルを作る。出力はコース一覧（概要＋コースカード＋コース追加プロンプト）と、コースごとの 1 ページ（左に Step ナビ、右にその Step の内容、左上に戻るボタン）。画面に出る文章のうちタイトルとソースコード以外は、このスキルが受講者向けに書き起こす（copy JSON）。lesson.yaml は記録であって教材の本文ではないため、そのまま転記しない。出典は各 Step からリンクで出典一覧に飛べ、日本語の要旨と公式の原文を併記する。origin などの作り手向けメタ情報は画面に出さず、ビルド時の検査に使う。HTML はテンプレート固定で、AI が HTML を書くことはない。コースは追記式。手を動かす教材を HTML にしたいときに使う。先に generate-lesson-yaml で YAML を作る。
---

# generate-lesson-html

`lesson.yaml`（教材の骨格）＋ `evidence.yaml`（逐語の根拠）＋**受講者向けに書き起こした
文章**を、オフラインで完結する HTML バンドルにするスキル。

```
index.yaml（doc-index/v1・任意）
lesson.yaml + evidence.yaml（generate-lesson-yaml の出力・1 コースにつき 1 組）
copy JSON（このスキルが書く受講者向けの文章）
        ↓ テンプレートに流し込む
バンドル: index.html            コース一覧（概要 / コース / コース追加プロンプト）
          views/<course>.html   コース本体（左: Step ナビ / 右: その Step / 左上: 戻る）
```

## 中心にある考え方: 記録と本文は別物

`lesson.yaml` は**記録**である。「なぜこの手順を置いたか（`why`）」「何が確認できるか
（`expect`）」は作り手のためのメモで、そのまま画面に出すと事務的な箇条書きになる。

そこで**受講者が読む文章はすべて書き起こす**。

| 画面に出るもの | どこから来るか |
|---|---|
| タイトル、ファイルパス、ソースコード、前提、確認の種別、出典の原文 | `lesson.yaml` / `evidence.yaml` |
| 導入・コードの説明・注意書き・確認の言い回し・出典の日本語要旨 | **copy JSON（書き起こす）** |
| `origin` / `origin_note` / `needs_facts` / fact の id / YAML のファイル名 | **画面に出さない** |

`origin` は消えたわけではない。**ビルド時に規則を検査**し、違反を警告として作り手に出す。
受講者に見せないだけ。

## このスキルが保証すること / しないこと

- **保証する — 受講者が読める日本語。** 文章は書き起こし、固有名詞は `` ` `` で囲んで
  視認性を上げ、出典は 1 タップ先に置く。
- **保証する — 追跡可能性。** 各 Step から出典一覧へ飛べ、日本語の要旨と**公式の原文**が
  併記される。どの記述に基づくかを受講者自身が確かめられる。
- **保証する — オフライン自己完結。** 外部 CDN / 通信 / ストレージ / cookie を使わない。
  `validate_html.py` が機械的に検査する。
- **保証しない — ビルドが通ること。** `lesson.yaml` 側の性質で、HTML 化では変わらない。
- **やらない — 事実の追加。** 書き起こすのは**説明**であって仕様ではない。YAML に無い API の
  挙動・手順・注意点を文章で足さない。足りないなら `generate-lesson-yaml` に戻る。

## 姉妹スキルとの違い（重要）

`generate-explainer-html` は**組み立て役**で、ビューの HTML は AI が毎回書き起こす。
このスキルは**レンダラ**で、HTML は `templates/` に固定されている。

- **AI は HTML を書かない。** 書くのは文章（copy JSON）だけ。マークアップの唯一の出所は
  `templates/index.html` と `templates/course.html`。レイアウトを変えたいときは
  **テンプレートを直す**（生成物を手で直さない）。
- **iframe を使わない。** コースは普通のリンクで開く 1 ページで、戻るボタンで一覧に戻る。
  そのため Chrome/Edge でも `file://` のまま開ける。
- **切り替える単位はビューではなくコース。**

## 出力（バンドル）

```
<bundle>/
  index.html                 コース一覧。views/<course>.html へリンクする
  courses.json               コースの順序付きマニフェスト
  copy.json                  受講者向けの文章（--copy をマージして保存・再ビルドで保持）
  prompts.json               コース追加プロンプト（コピーされる）
  index.yaml                 コピーされる（対応環境の取得元。プロンプトが絶対パスで引用）
  courses/<course>/lesson.yaml
  courses/<course>/evidence.yaml
  views/<course>.html        コース 1 つ = 1 ページ
```

コースは**追記式**。新しい `--lesson` を足して再実行すると、既存のコースを保ったまま
1 コース増える（同じ id で再実行するとそのコースだけ更新される）。

## 手順

1. **YAML を受け取り、読む。** `lesson.yaml` と `evidence.yaml`（隣に置かれている前提）の
   絶対パス、および元になった `index.yaml`。無ければ先に `generate-lesson-yaml` を
   実行する（索引が無ければ `generate-doc-index` から）。

2. **受講者向けの文章を書き起こす（このスキルの本体）。** copy JSON を書く。
   形とルールは `references/copy-contract.md`、実例は `references/sample-copy.json`。

   - コース一覧の概要、コースの導入、各 Step の導入、各コードの説明、注意書き、確認の
     言い回し、各出典の日本語要旨。
   - **話し言葉に近いですます調**で、声に出して読める文章にする。
   - **`lesson.yaml` の文を写さない。** `why` を語り直す。`expect` を言い換える。
   - **導入は「なぜ今これをやるのか」から。** 前の手順との繋がりを必ず書く。
   - **固有名詞は `` ` `` で囲む**（`<code>` として描画される）。
   - **先回りして不安を消す。**「この時点ではまだビルドが通りません」のような一文を
     `notes` に置く。
   - **作り手のメタ情報（origin・fact の id・YAML のファイル名）を書かない。**

3. **コース追加プロンプトを用意する。** `prompts.json`（配列）。既定のカードは
   `references/sample-prompts.json`。各カードはパスを `{{…}}` で引用し、**中身は貼らない**。
   型は `references/prompt-template-patterns.md`。

4. **バンドルをビルドする。** `scripts/build_lesson_html.py`（下記）。

5. **警告を読む。** ビルドは次を警告する。**警告が出たら YAML か copy を直す。**
   HTML 側で辻褄を合わせない。
   - copy が無い箇所（その項目は YAML の転記になっている）
   - `origin` の規則違反（`source_refs` の件数 / `origin_note` の有無）
   - 存在しない `source_refs`、どこからも参照されない fact、`step.id` の重複

6. **検証する。** `scripts/validate_html.py` を `index.html` と全 `views/*.html` に
   `--strict` で実行し、0 で終了するまで直す。

7. **渡す。** バンドルのフォルダと開き方、コース数・手順数を報告する。あわせて
   `origin` の内訳（特に `authored` の件数）も**作り手向けの情報として**報告する。

## コースをあとから足す（追記フロー）

```bash
python3 scripts/build_lesson_html.py --bundle <dir> \
  --lesson /abs/path/lessons/<新しいコース> --copy /abs/path/<新しい copy>.json
```

`courses.json` に追記され、`index.html` にカードが 1 枚増える。既存のコースページ・
`index.yaml`・`prompts.json`・既存の文章はそのまま残る（copy はマージされる）。

## スクリプトの使い方

```bash
python3 scripts/build_lesson_html.py \
  --bundle ./lesson-bundle \
  --index /abs/path/index.yaml \
  --lesson /abs/path/lessons/spotlight \
  --copy /abs/path/copy.json \
  --prompts references/sample-prompts.json
```

- `--bundle` のみ必須。
- `--lesson` は**繰り返し可**。ディレクトリ（`lesson.yaml` + `evidence.yaml` が入っている）
  でも `lesson.yaml` のパスでもよい。`evidence.yaml` は隣から探す
  （`sample-lesson.yaml` → `sample-evidence.yaml` のような対応も見る）。
  `--lesson "コースID=パス"` で URL / ファイル名になる id を明示できる（既定は
  `project.name` から作る）。
- `--copy` は受講者向けの文章。バンドルの `copy.json` に**マージ**され、省略すると
  保存済みのものが使われる。部分的に渡してよい。
- `--index` は対応環境のチップとプロンプトの参照先に使う。概要文には使わない
  （英語の原文を転記しないため）。
- `--prompts` / `--index` は省略するとバンドル内の既存ファイルを使う。

検証（オフライン安全性）:

```bash
python3 scripts/validate_html.py ./lesson-bundle/index.html ./lesson-bundle/views/*.html --strict
```

## 開き方

- **iframe を使っていないので、Chrome / Edge / Firefox のどれでも `file://` のまま開ける。**
- 右上のトグルでライト / ダーク。ストレージを使わない規約なので、テーマは**リンクのハッシュ**
  （`#theme=dark`）で一覧 ↔ コース間を引き継ぐ。リロードすると既定のライトに戻る。
- コースページのハッシュは `#step=<step id>` / `#fact=<fact id>`。特定の手順や出典を指して
  共有できる。

## うまくいかないとき

- **`copy.courses['…'] がありません`** — そのコースの文章が未執筆で、画面が `lesson.yaml` の
  転記になっている。copy JSON を書いて `--copy` で渡す。
- **`copy.facts に '…' の日本語要旨がありません`** — 出典一覧にその項目の要旨が出ない。
- **`build_lesson_html.py: could not parse …`** — 同梱の YAML ローダ（`mini_yaml.py`）は
  サブセット実装。アンカー（`&` / `*`）・タグ（`!!`）・複数ドキュメントは未対応。行番号が出る。
- **`evidence.yaml が隣にありません`** — 出典が空のバンドルになる。`lesson.yaml` と同じ
  ディレクトリに置くか、ファイル名を `<prefix>evidence.yaml` に合わせる。
- **`source_ref '…' が evidence.yaml に見つかりません`** — 束縛が壊れている。出典リンクが
  作られない。YAML 側を直す。
- **`fact '…' がどこからも参照されていません`** — 取得が要求ではなくドキュメント構造に
  引きずられた形跡。その fact を削るか束縛する。
- **`validate_html.py` が `http://` / `https://` で落ちる** — `path` や文章に URL スキームが
  残っている。スキームを落とす（`developer.apple.com/documentation/...`）。
- **レイアウトを変えたい** — `templates/` を直してから再ビルドする。生成された HTML を
  手で直すと次のビルドで消える。

## 同梱サンプルで試す

```bash
python3 scripts/build_lesson_html.py \
  --bundle ./sample-bundle \
  --index ../generate-doc-index/references/sample-index.yaml \
  --lesson ../generate-lesson-yaml/references/sample-lesson.yaml \
  --copy references/sample-copy.json \
  --prompts references/sample-prompts.json

python3 scripts/validate_html.py ./sample-bundle/index.html ./sample-bundle/views/*.html --strict
```

`sample-bundle/index.html` を開くと、App Intents の索引から作った 1 コース（4 手順・
出典 6 件）が並ぶ。`sample-copy.json` が、期待する文章の密度と文体の実例になっている。

## 参照

- `references/copy-contract.md` — **受講者向け原稿（copy JSON）の形と書き方**
- `references/sample-copy.json` — 4 手順分の原稿の実例
- `references/template-contract.md` — テンプレートの差し込み口と、何を画面に出す / 出さないか
- `references/bundle-structure.md` — バンドルの構造と 2 つの画面
- `references/html-generation-rules.md` — 安全性・オフライン・テーマ・アクセシビリティの規約
- `references/prompt-template-patterns.md` — コース追加プロンプトの型とパスの置換
- `references/sample-prompts.json` — 既定のコース追加プロンプト 4 種
- `templates/index.html` / `templates/course.html` — 出力される HTML の唯一の出所
- `scripts/mini_yaml.py` — 標準ライブラリだけの YAML サブセットローダ
- YAML スキーマ（前段のスキル）: `../generate-lesson-yaml/references/`
  （`lesson-yaml-schema.md`, `evidence-yaml-schema.md`）、
  `../generate-doc-index/references/doc-index-yaml-schema.md`
