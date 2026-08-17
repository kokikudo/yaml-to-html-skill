# メモ概要
このメモはハンズオン教材自作Skillの参考となる当リポジトリのSkillについての個人メモである。
Skillの文章は汚さず、気になることは全てこのmdに記載する。

## generate-explainer-yaml
**generate-explainer-yaml**にはこのSkillの役割と生成する成果物(相方のSkillの成果物含む)の概要がある。また、次に実行する**generate-explainer-html**との関係（全体フローの前半部分を担当する内容）が書かれている

**core.yaml**の各ラベルは以下
- コンセプト
- 他の意味との関連性
- 重要度
- 難易度
- 確信度
- 疑問点？
- リスク？
- 参照もと

**view.yaml**
- 対象読者
- 推奨、非推奨のフォーマット
- 密度？
- トーン？
- 強調
- 生成方針


**生成場所**は`./explainer-bundle/`に格納される。HTML生成時は格納場所の絶対パスを参照する。
使い捨ての一時パスは使用しないこと。

**処理Step**には各処理について具体的に記載がある。最後の項目に既存のcore.yamlの編集方法が書かれてる

**Note**には以下の内容が記されてる。
- core.yamlは閲覧環境に依存しないが、view.yamlは依存する。意味と表現を分けることでcore.yamlを別の購読者向けに再利用できる
- quiz.yamlは事実に基づくべき。正解なcore.yamlの内容と整合していること。誤答を選択肢として追加するのは許可するが、なぜ間違いなのかの解説は必ず入れる
- クイズはデフォルトで生成される。ユーザーの指示でSkipできる
- オフラインの安全性は全てのフローで担保されなければならない
  - 成果物のHTMLにはオンラインに関わるコード(htpp://, https://)をバリデートしている。
  - ソース内のリファレンス参照として配置するURLはラベルとして扱う
  - URLについての詳細はreferences/のmdを参考にする

### リファレンスのメモ(generate-explainer-yaml/references/)
- `references/core-yaml-schema.md` — meaning structure schema (`core/v1`)
  - スキーマに各フィールドの構造と列挙値が記載されてる
  - 重要度と難易度が高いほどUIの視覚的強調が高まる
  - 信頼度が低い場合は懸念事項や質問としてUIに載せる（＝信頼度が高いソースと隔離する）
- `references/view-yaml-schema.md` — presentation strategy schema (`view/v1`)
- `references/quiz-yaml-schema.md` — comprehension-check quiz schema (`quiz/v1`)
- `references/sample-core.yaml` — worked `core.yaml` (a PR)
- `references/sample-view.yaml` — worked `view.yaml` (engineer reviewing the PR)
- `references/sample-quiz.yaml` — worked `quiz.yaml` (all five item types, same PR)
- `references/examples.md` — three worked intents (engineer / PdM / beginner)
- `agents/openai.yaml` — portable description of this skill for non-Claude agents


### ハンズオン教材Skillはどう書くか
#### フローがそもそも違う
元のスキルはあらかじめ読者を指定し関連する情報のみ取得＆圧縮しyaml生成、その後に柔軟にUIを生成する。
これが実現できている理由はソースが構造化されていない完結されている文書だから（PR、Issue、何かしらのmd）。

ハンズオンはソースが構造化されていることを想定し、かつ読者の特定がHTML時なので前提が結構違う。

対策１
ソース内の各ページを並列でWeb Fetchしにそれぞれyamlファイルを生成。
それらをスキーマとして定義した管理用yamlを参照してHTML化させる。
-> 全てのページに対してyaml生成すると時間がかかるしWebにあるドキュメントをただローカルに移してるだけなのでスマートじゃない。

対策２
ソース内にリンクがある場合はそのリンクタイトル、前後の文脈から意味を抽出する。
既存のconceptsフィールドにsource_refsがあるのでそこにURLをのせる。
可能なら各リンクを一まとめにできそうならする。
こうすればHTML化時に初めてWeb Fetchで読み込むのでyamlファイルが肥大化しない。
AIがプロンプトに合わせてフェッチするページを判断するのでSKillらしい。
>例 (App Intents から抜粋)
> Widgets, controls, and Live Activities can use your app’s actions to perform relevant tasks.
> Widgets, contorols, Live Activitiesは『App Intentが提供するユーザーがアクションできるコンポーネント群』としてカテゴライズできる。
```
concepts:
  - id: components            
    label: App Intentのコンポーネント         
    kind: concept
    summary: App Intentが提供するコンポーネント群      
    detail: App Intentが提供するコンポーネント群。これら全てがそれぞれの表現方法によってアプリを開かなくてもユーザーがアクションできる         
    importance: high
    difficulty: medium
    confidence: 0.8  
    source_refs: 
      - id: c_widgets
        path: "https://developer.apple.com/documentation/WidgetKit"
      - id: c_controls
        path: "https://developer.apple.com/documentation/WidgetKit/Controls-Collection"
      - id: c_live_activities
        path: "https://developer.apple.com/documentation/activitykit"
```

対策３
以下のフローに一新する。ひとまずはAppleドキュメントのみで進める。
source(Apple Docs) -> index.html -> lesson.yaml -> evidence.yaml -> lession.yaml -> view.yaml

#### 探索範囲
App IntentsのAppleドキュメントのURLを渡したところ、読む関連記事とそうでない関連記事がある。
ハンズオンにとって貴重なコード例が書かれてるドキュメントなどを参照していない場合はAIが想定してコードを教材に差し込む可能性がある。


#### 人物像、ゴール設定
`generate-explainer-yaml`実行時に人物像とゴールの設定まで完了してview.yamlが生成されてしまう。
ハンズオンはHTML生成するときに読者と教材内容をプロンプトで指定したい。
**変更案1**: view.yamlを保持せず、HTML生成Skillを叩くときに人物像特定->ゴール特定->view.yamlの内容をYAML形式ファイルとして生成せずにHTML生成パイプラインに繋ぐ。
**変更案2**: view.yamlは生成し、audienceとintentフィールドはこの時点では作らない。HTML生成Skill実行時に人物像とゴールを特定後に上記フィールドを追加し他フィールドを更新する

## generate-explainer-html
descriptionにスキルの役割のほかに、ライトモードダークモード対応、ペインの説明、iframeデビューを切り替え、ビューを追加するためのプロンプトテンプレートのボタン、先にyamlを作成する必要がある、等が書かれてる。

iframeでのビューの種類はview.yamlのformsが元になる。

左ペインのプロンプトコピーはいらないと考えていたが、次の教材作成として使えそうかも。

`build_html.py`でHTMLを構築している。教材のフォーマットを指定するならスクリプト組む必要ないかも？

同じ内容のhtmlファイルが2つ作られてる？（01-エンジニア.htmlとengineer.htmlなど）

### refeerence/
html-generation-rules.md — 生成ルールの本体
- 出力はindex.html(シェル、build_html.pyが唯一の作者)＋views/NN-<id>.html(iframeビュー文書、AIが書く担当範囲)というバンドル構造
- 安全性の絶対ルール：外部script/CSS/iframe、fetch/XMLHttpRequest/WebSocket、localStorage/sessionStorage/cookie、window.parent/window.topアクセス、トップナビゲーション、APIキー埋め込みなどを全面禁止(validate_html.pyが機械的にスキャン)
- iframeはsandbox="allow-scripts"必須・allow-same-originは禁止(親から隔離するため)
- 各ビュー文書はライトテーマがデフォルトで、シェルからは#theme=dark|lightというURLハッシュ経由でテーマを受け取り、自分のlocation.hashを読んでhashchangeもlistenする
- 内容面では「重要概念・関係性・次に読むべき箇所・出典・次にAIに聞くべき質問」を必ず含め、progressive disclosure・アクセシビリティ・レスポンシブ・prefers-reduced-motion配慮も求める

quiz-view-rules.md — クイズビュー専用の追加ルール
- クイズは既定で作る(明示的な辞退がない限り)view
- 問題形式ごとの描画方法(single_choice/relationはradio、multiple_choiceはチェックボックス+採点ボタン、true_falseは○×、orderingはドラッグ&ドロップ禁止でクリック順並べ+やり直し)
- 採点は即時・iframe内完結。multiple_choiceは集合一致、orderingは完全順序一致、それ以外は単一正解ID一致
- 採点後は入力をdisabledにしてスコアの正直性を担保、「もう一度」で全リセット
- スコアはDOM/JS状態のみ保持(ブラウザストレージ禁止なのでリロードで消える旨を画面に明記)
- 読者(view.yamlのaudience)に応じて出題順を生成時に決める(初心者=易しい問題から、エンジニア=関係あて/並べ替えを先に)

output-bundle-structure.md — バンドル全体の構造説明
- index.html(ヘッダー+左ペインのプロンプトカード＋YAML閲覧+右ペインのビュー切替タブ＋iframe1枚)、views.json(ビュー一覧のマニフェスト)、コピーされたcore.yaml/view.yaml/quiz.yaml、views/配下の各ビューファイル、という構成を規定
- views.jsonが唯一の真実源で、再ビルドは既存ビューを保ったまま新規ビューを追記する

prompt-template-patterns.md — 左ペインの「ビュー追加」プロンプトカードの作り方
- 各カードは新しいiframeビューを1つだけ生成させるもので、シェルや他のプロンプト自体を書き換えさせない
- {{core_yaml_path}}/{{view_yaml_path}}/{{quiz_yaml_path}}というプレースホルダーにYAMLの絶対パスが埋め込まれる(中身は埋め込まない)
- 最低限含めるべき7種類のテンプレート：テーブル/ワークツリー/初心者向け/エンジニア向け/PdM・Biz向け/クイズ/自由記述
- プロンプト文中でfetch(などの禁止トークンをうっかり書くとvalidatorに引っかかるので、婉曲的な言い回しにする、という注意点

examples.md
- エンジニア向けPR理解(worktree+reading_path+review_checklist→後でtable追加)、PdM向けスペック理解(impact_map+decision_map+faq→後でFAQ追加)、初心者向けドキュメント理解(beginner_tutorial+glossary+faq→後でglossary追加)という3つの実例を通じて、「同じcore.yamlに複数のview.yaml/ビューを重ねていく」という使い方パターンを示している


## ディレクトリ構成
```
<bundle>/
  index.yaml
  main.html
  lessions/
    <lession_name>/
      <lession_name>.html
      lession.yaml
      narration.json
      cources.json
      evidence.yaml
```

### Sample
```
<reality_kit>/
  index.yaml
  main.html
  lessions/
    <rcs_minimam>/
      <rcs_minimam>.html
      lession.yaml
      narration.json
      cources.json
      evidence.yaml
    <attachment_view>/
      <attachment_view>.html
      lession.yaml
      narration.json
      cources.json
      evidence.yaml
```

# TODO
- [ ] Step -> 出典　へ遷移時に戻れるようにする
- [ ] 受講者のペルソナを確定する
    - [ ] ゴール（何をできるようになりたいか）
    - [ ] スコープの確認：何を学んで何を除外するか
    - [ ] 言語の開発レベル
        - [ ] あくまで参考程度。レベルが低い人向けに追加の解説を入れるくらい
- [ ] 最後のStepに自力て実装できるようにクイズを出す
- [ ] 資料作り
    - [ ] 5分スピーチ向け
        - [ ] フローの大枠を理解する
        - [ ] 話す内容を厳選する
    - [ ] ギャップロ
        - [ ] 処理の流れを理解する
            - [ ] 記事には出力例を載せ、細かい処理は説明しない
            - [ ] フロー図は必須
            - [ ] なぜYAML化する必要があるのかの説明
- [ ] generate-lesson-yaml -> generate-lesson-html を止めずに回す
    - [ ] これによってファイルとして残さなくても良いものを生成しないようにする
        - [ ] 残さなくていいもの：出力不具合時に確認しなくていいもの→ スコープを確認する
    - [ ] ユーザーには何を確認させたいか考える
        - [ ] yamlを見る必要ある？ないならすべてのフローを単体SKILLで実行させて良いのでは？
            - [ ] yamlを逐一確認はしないが、AIが回答した懸念事項によって修正は発生しうる可能あり