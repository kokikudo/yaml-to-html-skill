# バンドルの構造

成果物は**ディレクトリ**。1 ファイルではないのは、レッスンを 1 つずつ**追記**できるようにする
ため（レッスンが増えてもページは増えるだけで、既存のページは書き換わらない）。

```
<bundle>/
  index.yaml                  索引（generate-doc-index が作る）。出所の記録。ビルドは読まない
  narration.json              main.html の中身（title / lead / availability / notes / source_note）
  lessons.json                レッスンの順序付きマニフェスト（ビルドが生成）
  main.html                   レッスン一覧（概要 / レッスンカード）
  lessons/
    <lesson_id>/
      lesson.yaml             generate-lesson-yaml の出力
      evidence.yaml           generate-lesson-yaml の出力
      narration.json          このレッスンの文章（このスキルが書く）
      <lesson_id>.html        レッスン本体。1 レッスン = 1 ページ
```

`main.html` と `<lesson_id>.html` と `lessons.json` は**ビルドの生成物**。手で直さない
（次のビルドで消える）。それ以外は入力なので、手で書いてよい。

レッスンに要るものは `lessons/<lesson_id>/` に揃っているので、1 レッスンをそのまま別の
バンドルへ移せる。

画面に出る文章のうち、**タイトルとソースコード以外は `narration.json` から来る**。`lesson.yaml`
は記録であって教材の本文ではないため（→ `narration-contract.md`）。

**ビルドの入力は `lesson.yaml` / `evidence.yaml` / `narration.json` の 3 つだけ。**
`index.yaml` は上流（`generate-lesson-yaml`、および narration を書く工程）の入力であって、
`build_lesson_html.py` は読まない。バンドルに置いてあるのは「この教材がどの索引から生えたか」
を残すため（次にレッスンを足すとき、概要を書き直すのに読む資料でもある）。ビルドに索引を
渡すフラグは無い。

`scripts/build_lesson_html.py` がこの形を作り、維持する。

## iframe を使わない

姉妹スキル `generate-explainer-html` は右ペインの iframe でビューを差し替えるが、
このバンドルは**普通のページ遷移**でレッスンを開く。

- レッスンカードは `<a href="lessons/<lesson_id>/<lesson_id>.html">`、レッスンページの
  戻るボタンは `<a href="../../main.html">`。
- そのため **Chrome / Edge でも `file://` のまま開ける**（Chrome は `file://` の iframe
  読み込みだけをブロックする。リンク遷移はブロックされない）。
- ハンズオンは「1 つの手順を集中して読む」画面なので、同一ページ内で切り替える対象は
  ビューではなく **Step** になる。

## 画面 1: レッスン一覧（`main.html`）

```text
header            narration の title + ライト/ダークトグル
概要              索引が指すドキュメントの概要（書き起こした文章）+ 対応環境チップ
レッスン          レッスンカードのグリッド。1 枚 = 1 レッスン
                    タイトル / narration の summary / 手順数 / stack
inline <style> / <script>   外部 CSS・JS なし
```

- **概要が説明するのは「索引が指すドキュメント」**。`index.yaml` が
  `developer.apple.com/documentation/realitykit` の索引なら、`RealityKit` が何なのかを書く。
  そこに何本レッスンがあるかはカードが示すので、概要では触れない。
- ただし `index.yaml` の `root_abstract`（英語の原文）は**転記しない**。それを日本語に
  書き起こした文章をバンドル直下の `narration.json` の `lead` から出す。無い場合は
  プレースホルダになり、ビルドが警告する。
- **見出しもチップも `narration.json` から出す**（`title` / `availability`）。索引を読んで
  それらを書くのは narration を書く工程の仕事で、ビルドの仕事ではない。無ければ見出しは
  既定値になって警告、チップは出ない。
- カードは `lessons.json` の順。

## 画面 2: レッスン本体（`lessons/<lesson_id>/<lesson_id>.html`）

```text
header       < レッスン一覧（戻る）+ レッスン名 + ライト/ダークトグル
左ペイン      レッスンの Step
               概   レッスンの概要
               1    最初の手順
               2    …
               典   出典一覧
右ペイン      選択中の 1 項目だけを表示
               概要   : 導入 / 終えたときの状態 / 前提 / 下ごしらえ / 扱う範囲
               各 Step: 導入 / 書くコード（説明つき）/ 注意書き / 確認 / つまずき / 出典
               出典   : タイトル → パス → 日本語要旨 → 原文 → メタ情報
下部          前へ / 次へ（隣の項目のタイトルが出る）
```

- 各 Step の「この手順のもとになった資料」から、出典一覧の該当エントリへジャンプできる
  （同じページ内。該当箇所までスクロールして一瞬強調する）。

- 表示の切り替えはページ内で完結する（パネルの表示/非表示）。ネットワークもストレージも使わない。
- URL ハッシュは `#step=<step id>` / `#fact=<fact id>`（ダーク時は `&theme=dark`）。
  特定の手順や出典を指して共有できる。

## マニフェスト（`lessons.json`）

レッスン一覧の唯一の真実源。カードの内容も並び順もここから決まる。**バンドル直下に 1 つ**
だけ置く（レッスンをまたぐ順序を持つ情報なので、レッスンのディレクトリの中には置けない）。

ビルドは `lessons/` にあるレッスンを毎回すべて描き直し、`lessons.json` を書き直す。
既存のエントリの順序は保たれ、新しいレッスンは末尾に足される。ディレクトリごと消したレッスンは
一覧からも消える。

1 エントリが持つもの: `id` / `file`（バンドルからの相対パス）/ `title` / `summary` / `stack` /
`steps` / `facts` / `origins`（origin 別の件数。**作り手向けの集計で UI には出さない**）/
`truncated`。

## 出力の安全性

- 通信なし・外部スクリプト/CSS なし・ストレージなし・cookie なし・秘密情報なし。
- `scripts/validate_html.py` が `main.html` と全 `lessons/*/*.html` を検査する。
- 教材のコードはそのまま `<pre>` に入る（HTML エスケープ済み）。実行はされない。
- `narration.json` の文章も段落と `<code>` にしか変換されない（HTML は解釈しない）。
