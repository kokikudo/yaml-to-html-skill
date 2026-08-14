#!/usr/bin/env python3
"""build_lesson_html.py

Render a hands-on **lesson bundle** from one or more ``lesson.yaml`` / ``evidence.yaml``
pairs (lesson/v1 + evidence/v1) and the **narration files** holding the reader-facing
Japanese prose. Those are the only inputs: ``index.yaml`` belongs to the upstream skills
(it is what the narration author read to write the overview), and the build never reads it.

Two kinds of input, on purpose
------------------------------
``lesson.yaml`` is a *record*: what to build, in what order, with what evidence. Rendered
verbatim it reads like a spec, not like teaching material. So the page takes:

- **from the YAML** — titles, file paths, source code, requirements, checkpoints, sources;
- **from the narration files** — every explanatory sentence the learner reads (lesson
  lead-in, per-step lead-in, per-file explanation, cautions, checkpoint wording, and the
  Japanese gist of each quoted source).

Author metadata (``origin``, ``origin_note``, ``needs_facts``, fact ids, YAML file names)
stays out of the learner-facing UI. The origin rules are still *checked* — violations are
reported as build warnings for the author.

The markup itself lives in ``templates/`` and is the single source of truth for layout:

    templates/main.html     the lesson list  (概要 + レッスン)
    templates/lesson.html   one lesson       (left: Step nav / right: the current Step)

What it produces
----------------

    <bundle>/
      index.yaml                 the doc index the material came from, left where the
                                 upstream skills put it. Not read by this script.
      narration.json             everything main.html shows (title / lead / availability /
                                 notes / source_note)
      lessons.json               ordered manifest: {"lessons":[{id,file,title,...}, ...]}
      main.html                  lesson list; links to lessons/<id>/<id>.html
      lessons/<id>/lesson.yaml
      lessons/<id>/evidence.yaml
      lessons/<id>/narration.json    prose for this lesson
      lessons/<id>/<id>.html        the lesson page

Everything a lesson needs lives in its own directory, so a lesson is self-contained on
disk and the bundle is what the two upstream skills write into directly.

There is **no iframe**: a lesson is a normal page reached by a link, and the back link
returns to the list. That keeps the bundle openable in any browser over ``file://``.

Lessons are **additive**. Every build renders every lesson directory found under
``lessons/``; ``--lesson`` imports one more from outside the bundle.

Example
-------
    python3 scripts/build_lesson_html.py --bundle ./lesson-bundle

    python3 scripts/build_lesson_html.py \
      --bundle ./lesson-bundle \
      --lesson spotlight=/abs/path/elsewhere/spotlight \
      --narration spotlight=/abs/path/narration.json
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mini_yaml  # noqa: E402  (local, stdlib-only helper)


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# origin is author metadata: it is checked, never shown to the learner.
ORIGIN_RULES = {"verbatim_from_doc", "adapted", "synthesized", "authored"}
ORIGIN_ORDER = ["verbatim_from_doc", "adapted", "synthesized", "authored"]

ACTION_LABELS = {"create": "新規作成", "update": "書き足す"}
# 作る / 足す を色で見分けられるようにする（テンプレート側の .badge.create / .badge.update）
ACTION_BADGE_CLASSES = {"create": "create", "update": "update"}
CHECKPOINT_LABELS = {
    "build": ("ビルドして確認", "ビルドが通ることを確かめる"),
    "run": ("動かして確認", "実際に実行して確かめる"),
    "observe": ("目で見て確認", "画面を見て確かめる。自動では判定できない"),
}
FACT_KIND_LABELS = {
    "concept": "概念",
    "declaration": "宣言",
    "code_example": "コード例",
    "constraint": "前提・制限",
    "procedure": "手順",
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def esc(text: object) -> str:
    """HTML-escape a value for safe display (quotes included)."""
    return html.escape("" if text is None else str(text), quote=True)


_CODE_SPAN_RE = re.compile(r"`([^`]+)`")


def inline(text: object) -> str:
    """Escape text, then turn `backticked` proper nouns into <code> spans.

    Type names, API names and file names are wrapped in backticks by the narration author so
    they stand out in a wall of Japanese prose.
    """
    return _CODE_SPAN_RE.sub(r"<code>\1</code>", esc(text))


def prose(text: object, css_class: str = "") -> str:
    """Render a possibly multi-paragraph string as <p> elements (with inline code spans)."""
    if not text:
        return ""
    attr = f' class="{css_class}"' if css_class else ""
    blocks = [b.strip() for b in str(text).split("\n\n") if b.strip()]
    return "\n".join(f"<p{attr}>{inline(b)}</p>" for b in blocks)


def read_text(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"build_lesson_html.py: input file not found: {p}")
    return p.read_text(encoding="utf-8")


def load_yaml(path: str | Path) -> dict:
    try:
        data = mini_yaml.load(read_text(path))
    except mini_yaml.YamlError as exc:
        raise SystemExit(f"build_lesson_html.py: could not parse {path}: {exc}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SystemExit(f"build_lesson_html.py: {path} must contain a YAML mapping")
    return data


def load_json(path: str | Path, what: str) -> object:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"build_lesson_html.py: could not parse {what} ({path}): {exc}")


_DOC_COMMENT_RE = re.compile(r"^(\s*<!DOCTYPE[^>]*>)\s*<!--.*?-->", re.S | re.I)


def load_template(name: str) -> str:
    """Read a template and drop its leading maintainer comment.

    That comment documents the ``__TOKEN__`` slots, so it must go before substitution —
    otherwise the tokens listed there would be filled in as well (and a ``-->`` inside
    rendered content could break out of the comment).
    """
    return _DOC_COMMENT_RE.sub(r"\1", read_text(TEMPLATE_DIR / name), count=1)


def slugify(label: str) -> str:
    """Derive a filesystem/URL-friendly id (Unicode letters kept, so 日本語 stays readable)."""
    out = []
    for ch in str(label).strip().lower():
        out.append(ch if (ch.isalnum() or ch in "-_") else "-")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-_") or "lesson"


def as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def deep_merge(base: dict, overlay: dict) -> dict:
    """Merge ``overlay`` into ``base`` (dicts recurse, everything else is replaced)."""
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def copy_file(src: Path, dest: Path) -> None:
    """Copy text content, unless src and dest are the same file already."""
    if same_file(src, dest):
        return
    dest.write_text(read_text(src), encoding="utf-8")


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------

def index_facts(evidence: dict) -> dict[str, dict]:
    facts: dict[str, dict] = {}
    for fact in as_list(evidence.get("facts")):
        if isinstance(fact, dict) and fact.get("id"):
            facts[str(fact["id"])] = fact
    return facts


def fact_links(refs: object, facts: dict[str, dict], missing: list[str],
               label: str = "この内容の出典") -> str:
    """A line of links into the 出典一覧 page (never the raw fact id)."""
    ids = [str(r) for r in as_list(refs) if r]
    if not ids:
        return ""
    links = []
    for ref in ids:
        fact = facts.get(ref)
        if fact is None:
            missing.append(ref)
            continue
        title = fact.get("title") or (fact.get("source") or {}).get("page_title") or "出典"
        links.append(f'<a class="fact-link" href="#fact={esc(ref)}" data-fact="{esc(ref)}">'
                     f"{inline(title)}</a>")
    if not links:
        return ""
    return (f'<p class="ref-line"><span class="ref-label">{esc(label)}:</span> '
            f'{"、".join(links)}</p>')


# ---------------------------------------------------------------------------
# lesson page rendering
# ---------------------------------------------------------------------------

def render_overview_panel(lesson: dict, facts: dict[str, dict], narration: dict,
                          missing: list[str], warnings: list[str], lesson_id: str) -> str:
    goal = as_dict(lesson.get("goal"))
    project = as_dict(lesson.get("project"))
    scope = as_dict(lesson.get("scope"))
    parts: list[str] = ['<article class="panel" id="panel-overview">',
                        f'  <h2>{inline(goal.get("title") or "概要")}</h2>']

    if scope.get("truncated"):
        reason = narration.get("truncated_note") or scope.get("truncated_reason")
        parts.append(
            '  <div class="banner"><strong>このレッスンは途中までです。</strong> '
            f'{inline(reason)}</div>'
        )

    lead = narration.get("lead")
    if not lead:
        warnings.append(f"{lesson_id}: 解説文に lead がありません（概要が YAML の転記になります）")
    parts.append(prose(lead or goal.get("outcome"), "lead"))

    goal_text = narration.get("goal") or goal.get("outcome")
    if goal_text:
        parts.append('  <h3>このレッスンを終えたときの状態</h3>')
        parts.append(prose(goal_text))

    chips = []
    if project.get("stack"):
        chips.append(f'<span class="chip">{inline(project["stack"])}</span>')
    chips.append(f'<span class="chip">全 {len(as_list(lesson.get("steps")))} 手順</span>')
    parts.append(f'  <div class="chips">{"".join(chips)}</div>')

    requirements = [r for r in as_list(project.get("requirements")) if isinstance(r, dict)]
    if requirements or narration.get("requirements"):
        parts.append("  <h3>始める前に必要なもの</h3>")
        if narration.get("requirements_lead"):
            parts.append(prose(narration["requirements_lead"]))
        parts.append('  <ul class="plain-list">')
        rewritten = as_list(narration.get("requirements"))
        for position, requirement in enumerate(requirements):
            text = rewritten[position] if position < len(rewritten) else requirement.get("text")
            refs = fact_links(requirement.get("source_refs"), facts, missing, "出典")
            parts.append(f"    <li>{inline(text)}{refs}</li>")
        for extra in rewritten[len(requirements):]:
            parts.append(f"    <li>{inline(extra)}</li>")
        parts.append("  </ul>")

    scaffold_steps = as_list(narration.get("scaffold")) or \
        as_list(as_dict(project.get("scaffold")).get("steps"))
    if scaffold_steps:
        parts.append("  <h3>下ごしらえ（プロジェクトの用意）</h3>")
        if narration.get("scaffold_lead"):
            parts.append(prose(narration["scaffold_lead"]))
        parts.append("  <ol>" + "".join(f"<li>{inline(s)}</li>" for s in scaffold_steps) + "</ol>")

    covers = as_list(narration.get("covers")) or as_list(scope.get("covers"))
    excludes = as_list(narration.get("excludes")) or as_list(scope.get("excludes"))
    if covers or excludes:
        parts.append("  <h3>このレッスンで扱うこと</h3>")
        if covers:
            parts.append("  <ul>" + "".join(f"<li>{inline(c)}</li>" for c in covers) + "</ul>")
        if excludes:
            parts.append('  <p class="muted">扱わないこと</p>')
            parts.append("  <ul>" + "".join(f"<li>{inline(x)}</li>" for x in excludes) + "</ul>")

    for note in as_list(narration.get("notes")):
        parts.append(f'  <div class="note">{prose(note)}</div>')

    parts.append("</article>")
    return "\n".join(p for p in parts if p)


def render_step_panel(step: dict, number: int, total: int, facts: dict[str, dict],
                      narration: dict, missing: list[str], warnings: list[str],
                      lesson_id: str) -> str:
    step_id = str(step.get("id") or f"step-{number}")
    parts: list[str] = [f'<article class="panel hidden" id="panel-{esc(step_id)}">',
                        f'  <p class="eyebrow">Step {number} / {total}</p>',
                        f'  <h2>{inline(step.get("title") or step_id)}</h2>']

    lead = narration.get("lead")
    if not lead:
        warnings.append(f"{lesson_id}/{step_id}: 解説文に lead がありません"
                        "（導入文が YAML の転記になります）")
    parts.append(prose(lead or step.get("why"), "lead"))

    files = [f for f in as_list(step.get("files")) if isinstance(f, dict)]
    file_narration = as_dict(narration.get("files"))
    if files:
        parts.append("  <h3>書くコード</h3>")
    for position, file_item in enumerate(files, start=1):
        code_id = f"code-{slugify(step_id)}-{position}"
        path = str(file_item.get("path", ""))
        action_label = ACTION_LABELS.get(str(file_item.get("action", "")), "")
        lang = file_item.get("lang")
        explanation = file_narration.get(path) or file_narration.get(Path(path).name)
        # 並び順は 説明 → ファイル名 → コード。説明は枠の外に置き、枠で囲むのは
        # ファイル名（左上に「新規作成 / 書き足す」）とコードだけ。
        if explanation:
            parts.append(prose(explanation, "file-note"))
        parts.append('  <div class="file">')
        parts.append('    <div class="file-head">')
        badges = []
        if action_label:
            action_class = ACTION_BADGE_CLASSES.get(str(file_item.get("action", "")), "neutral")
            badges.append(f'<span class="badge {action_class}">{esc(action_label)}</span>')
        if lang:
            badges.append(f'<span class="badge lang">{esc(lang)}</span>')
        if badges:
            parts.append(f'      <span class="file-meta">{"".join(badges)}</span>')
        parts.append(f'      <code class="file-path">{esc(path)}</code>')
        parts.append("    </div>")
        parts.append('    <div class="code-wrap">')
        parts.append(f'      <button class="copy-btn" type="button" data-target="{code_id}"'
                     f' aria-label="{esc(path)} のコードをコピー">コピー</button>')
        parts.append(f'      <pre class="code" id="{code_id}">'
                     f'{esc(file_item.get("content", ""))}</pre>')
        parts.append("    </div>")
        parts.append(fact_links(file_item.get("source_refs"), facts, missing,
                                "このコードの出典"))
        parts.append("  </div>")

    for note in as_list(narration.get("notes")):
        parts.append(f'  <div class="note">{prose(note)}</div>')

    checkpoint = as_dict(step.get("checkpoint"))
    if checkpoint:
        kind = str(checkpoint.get("kind", ""))
        label, meaning = CHECKPOINT_LABELS.get(kind, ("確認", ""))
        parts.append("  <h3>ここまでの確認</h3>")
        parts.append('  <div class="checkpoint">')
        parts.append(f'    <span class="badge check" title="{esc(meaning)}">{esc(label)}</span>')
        parts.append(prose(narration.get("checkpoint") or checkpoint.get("expect"), "expect"))
        parts.append(fact_links(checkpoint.get("source_refs"), facts, missing,
                                "この確認の出典"))
        parts.append("  </div>")

    errors = [e for e in as_list(step.get("common_errors")) if isinstance(e, dict)]
    if errors:
        parts.append("  <h3>つまずいたときは</h3>")
        for error in errors:
            ref = error.get("source_ref")
            parts.append('  <div class="errors">')
            parts.append(f'    <p class="symptom">{inline(error.get("symptom"))}</p>')
            parts.append(f'    <p class="cause">{inline(error.get("cause"))}</p>')
            parts.append(fact_links([ref] if ref else [], facts, missing, "出典"))
            parts.append("  </div>")

    parts.append("</article>")
    return "\n".join(p for p in parts if p)


def render_evidence_panel(lesson: dict, facts: dict[str, dict], narration: dict,
                          warnings: list[str], lesson_id: str) -> str:
    """The last nav entry: every quoted source, gist first, original text alongside."""
    used_by: dict[str, list[str]] = {}

    def note_use(refs: object, where: str) -> None:
        for ref in as_list(refs):
            used_by.setdefault(str(ref), []).append(where)

    project = as_dict(lesson.get("project"))
    for requirement in as_list(project.get("requirements")):
        if isinstance(requirement, dict):
            note_use(requirement.get("source_refs"), "始める前に必要なもの")
    for number, step in enumerate(as_list(lesson.get("steps")), start=1):
        if not isinstance(step, dict):
            continue
        where = f"Step {number}"
        for file_item in as_list(step.get("files")):
            if isinstance(file_item, dict):
                note_use(file_item.get("source_refs"), where)
        checkpoint = step.get("checkpoint")
        if isinstance(checkpoint, dict):
            note_use(checkpoint.get("source_refs"), where)
        for error in as_list(step.get("common_errors")):
            if isinstance(error, dict) and error.get("source_ref"):
                note_use([error["source_ref"]], where)

    gists = as_dict(narration.get("facts"))
    parts = ['<article class="panel hidden" id="panel-evidence">',
             "  <h2>出典一覧</h2>",
             prose(narration.get("lead") or
                   "このレッスンの説明とコードが、公式ドキュメントのどの記述に基づいているかの"
                   "一覧です。各手順のコードや確認の下にある「出典」から、ここへ飛べます。")]
    if not facts:
        parts.append('  <p class="muted">出典が登録されていません。</p>')

    for fact_id, fact in facts.items():
        source = as_dict(fact.get("source"))
        gist = gists.get(fact_id)
        if not gist:
            warnings.append(f"{lesson_id}: 解説文の evidence.facts に '{fact_id}' の日本語要旨がありません")
        kind = FACT_KIND_LABELS.get(str(fact.get("kind", "")), str(fact.get("kind", "")))
        meta = ["ページ: " + str(source.get("page_title", "")) if source.get("page_title") else ""]
        if source.get("fetched_at"):
            meta.append(f"取得日: {source['fetched_at']}")
        users = sorted(set(used_by.get(fact_id, [])), key=lambda x: (x != "始める前に必要なもの", x))
        if users:
            meta.append("使う場面: " + "、".join(users))

        kind_badge = f' <span class="badge neutral">{esc(kind)}</span>' if kind else ""
        parts.append(f'  <article class="fact-entry" id="fact-{esc(fact_id)}">')
        parts.append(f'    <h3>{inline(fact.get("title") or fact_id)}{kind_badge}</h3>')
        if source.get("path"):
            parts.append(f'    <p class="fact-path">{esc(source["path"])}</p>')
        if gist:
            parts.append(prose(gist, "fact-gist"))
        parts.append('    <div class="fact-original">')
        parts.append('      <p class="fact-original-label">公式ドキュメントの原文</p>')
        parts.append(f'      <pre>{esc(fact.get("verbatim", ""))}</pre>')
        parts.append("    </div>")
        parts.append(f'    <p class="fact-meta">{esc(" ・ ".join(m for m in meta if m))}'
                     f'<span class="fact-id">{esc(fact_id)}</span></p>')
        parts.append("  </article>")

    parts.append("</article>")
    return "\n".join(p for p in parts if p)


def render_nav(items: list[tuple[str, str, str]]) -> str:
    """items: (step id, circle marker, label)."""
    lis = []
    for step_id, marker, label in items:
        lis.append(
            f'<li><button class="nav-btn" type="button" data-step="{esc(step_id)}"'
            f' data-label="{esc(label)}">'
            f'<span class="nav-num" aria-hidden="true">{esc(marker)}</span>'
            f"<span>{inline(label)}</span></button></li>"
        )
    return "\n        ".join(lis)


def render_lesson_page(lesson: dict, evidence: dict, narration: dict, back_href: str,
                       warnings: list[str], lesson_id: str) -> tuple[str, dict]:
    """Render one lessons/<id>/<id>.html; return (html, summary)."""
    template = load_template("lesson.html")
    facts = index_facts(evidence)
    missing: list[str] = []

    goal = as_dict(lesson.get("goal"))
    steps = [s for s in as_list(lesson.get("steps")) if isinstance(s, dict)]
    step_narration = as_dict(narration.get("steps"))

    nav_items: list[tuple[str, str, str]] = [("overview", "概", "レッスンの概要")]
    panels = [render_overview_panel(lesson, facts, narration, missing, warnings, lesson_id)]
    for number, step in enumerate(steps, start=1):
        step_id = str(step.get("id") or f"step-{number}")
        nav_items.append((step_id, str(number), str(step.get("title") or step_id)))
        panels.append(render_step_panel(step, number, len(steps), facts,
                                        as_dict(step_narration.get(step_id)), missing,
                                        warnings, lesson_id))
    nav_items.append(("evidence", "典", "出典一覧"))
    panels.append(render_evidence_panel(lesson, facts, as_dict(narration.get("evidence")),
                                        warnings, lesson_id))

    for ref in dict.fromkeys(missing):
        warnings.append(f"{lesson_id}: source_ref '{ref}' が evidence.yaml に見つかりません")

    document = template
    document = document.replace("__LESSON_TITLE__", inline(goal.get("title") or lesson_id))
    document = document.replace("__BACK_HREF__", esc(back_href))
    document = document.replace("__STEP_COUNT__", str(len(steps)))
    document = document.replace("__NAV_ITEMS__", render_nav(nav_items))
    document = document.replace("__PANELS__", "\n".join(panels))

    summary = {
        "title": str(goal.get("title") or lesson_id),
        "summary": str(narration.get("summary") or goal.get("outcome") or ""),
        "stack": str(as_dict(lesson.get("project")).get("stack") or ""),
        "steps": len(steps),
        "facts": len(facts),
        "origins": count_origins(lesson),
        "truncated": bool(as_dict(lesson.get("scope")).get("truncated")),
    }
    return document, summary


# ---------------------------------------------------------------------------
# main page rendering
# ---------------------------------------------------------------------------

def render_overview_section(narration: dict, warnings: list[str]) -> tuple[str, str, str, str]:
    """Return (page title, overview body, meta chips, closing note).

    Every part of this section comes from the bundle's ``narration.json`` — the same rule
    the rest of the page follows. The overview describes **the documentation the index
    points at**, not the lessons (the lessons have their own cards below it), but the
    narration author is the one who read the index and wrote that description in Japanese;
    the build never reads ``index.yaml``.
    """
    title = narration.get("title")
    if not title:
        warnings.append("narration.json に title がありません"
                        "（レッスン一覧の見出しが既定値になります。index.yaml の "
                        "source.root_title をもとに付けてください）")
    title = str(title or "ハンズオン教材")

    lead = narration.get("lead")
    if lead:
        body = prose(lead)
    else:
        warnings.append("narration.json に lead がありません"
                        "（レッスン一覧の概要が空になります。index.yaml の source.root_abstract を"
                        "日本語に書き起こしてください）")
        body = ('<p class="empty">このレッスン一覧の概要はまだ書かれていません。'
                'バンドル直下の narration.json に、索引が指すドキュメントが何であるかを'
                '日本語で書いた lead を入れてください。</p>')
    for note in as_list(narration.get("notes")):
        body += f'\n<div class="note">{prose(note)}</div>'

    chips = [f'<span class="chip">{esc(a)}</span>'
             for a in as_list(narration.get("availability"))]
    meta = f'<div class="chips">{"".join(chips)}</div>' if chips else ""

    note = ""
    if narration.get("source_note"):
        note = f'<p class="source-note">{inline(narration["source_note"])}</p>'
    return (title, body, meta, note)


def render_lesson_cards(lessons: list[dict]) -> str:
    if not lessons:
        return '<p class="empty">レッスンがまだありません。</p>'
    cards = []
    for lesson in lessons:
        chips = [f'<span class="chip">全 {lesson.get("steps", 0)} 手順</span>']
        if lesson.get("stack"):
            chips.append(f'<span class="chip">{esc(lesson["stack"])}</span>')
        if lesson.get("truncated"):
            chips.append('<span class="chip warn">途中まで</span>')
        cards.append("\n".join([
            f'<a class="lesson-card" href="{esc(lesson["file"])}">',
            f'  <h3>{inline(lesson["title"])}</h3>',
            f'  <p class="outcome">{inline(lesson.get("summary", ""))}</p>',
            f'  <div class="chips">{"".join(chips)}</div>',
            '  <span class="lesson-cta">はじめる →</span>',
            "</a>",
        ]))
    return "\n".join(cards)


# ---------------------------------------------------------------------------
# author-facing checks (never shown in the UI)
# ---------------------------------------------------------------------------

def count_origins(lesson: dict) -> dict[str, int]:
    counts = {key: 0 for key in ORIGIN_ORDER}

    def tally(item: object) -> None:
        if isinstance(item, dict) and item.get("origin") in counts:
            counts[str(item["origin"])] += 1

    project = as_dict(lesson.get("project"))
    tally(project.get("scaffold"))
    for requirement in as_list(project.get("requirements")):
        tally(requirement)
    for step in as_list(lesson.get("steps")):
        if not isinstance(step, dict):
            continue
        for file_item in as_list(step.get("files")):
            tally(file_item)
        tally(step.get("checkpoint"))
    return counts


def check_lesson(lesson: dict, facts: dict[str, dict], lesson_id: str,
                 warnings: list[str]) -> None:
    """Report the origin / source_refs rules the lesson skill checks (never fatal)."""
    used: set[str] = set()

    def audit(item: object, where: str) -> None:
        if not isinstance(item, dict) or "origin" not in item:
            return
        origin = str(item.get("origin"))
        refs = [str(r) for r in as_list(item.get("source_refs")) if r]
        used.update(refs)
        note = item.get("origin_note")
        if origin not in ORIGIN_RULES:
            warnings.append(f"{lesson_id}/{where}: 未知の origin '{origin}'")
            return
        if origin == "verbatim_from_doc" and not refs:
            warnings.append(f"{lesson_id}/{where}: verbatim_from_doc に source_refs がありません")
        if origin == "adapted" and (not refs or not note):
            warnings.append(f"{lesson_id}/{where}: adapted は source_refs 1 件以上と origin_note が必要です")
        if origin == "synthesized" and (len(refs) < 2 or not note):
            warnings.append(f"{lesson_id}/{where}: synthesized は source_refs 2 件以上と origin_note が必要です")
        if origin == "authored" and (refs or not note):
            warnings.append(f"{lesson_id}/{where}: authored は source_refs 空 + origin_note 必須です")

    project = as_dict(lesson.get("project"))
    audit(project.get("scaffold"), "project.scaffold")
    for position, requirement in enumerate(as_list(project.get("requirements")), start=1):
        audit(requirement, f"project.requirements[{position}]")
    seen_ids: set[str] = set()
    for number, step in enumerate(as_list(lesson.get("steps")), start=1):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id") or f"step-{number}")
        if step_id in seen_ids:
            warnings.append(f"{lesson_id}: step id '{step_id}' が重複しています")
        seen_ids.add(step_id)
        for position, file_item in enumerate(as_list(step.get("files")), start=1):
            audit(file_item, f"{step_id}.files[{position}]")
        audit(step.get("checkpoint"), f"{step_id}.checkpoint")
        for error in as_list(step.get("common_errors")):
            if isinstance(error, dict):
                if not error.get("source_ref"):
                    warnings.append(f"{lesson_id}/{step_id}: common_errors に source_ref がありません")
                else:
                    used.add(str(error["source_ref"]))

    for fact_id in facts:
        if fact_id not in used:
            warnings.append(f"{lesson_id}: fact '{fact_id}' がどこからも参照されていません")


# ---------------------------------------------------------------------------
# bundle assembly
# ---------------------------------------------------------------------------

def load_manifest(bundle: Path) -> list[dict]:
    path = bundle / "lessons.json"
    if not path.is_file():
        return []
    data = load_json(path, "lessons.json")
    lessons = data.get("lessons") if isinstance(data, dict) else None
    if not isinstance(lessons, list):
        return []
    return [entry for entry in lessons if isinstance(entry, dict) and entry.get("id")]


def write_manifest(bundle: Path, lessons: list[dict]) -> None:
    (bundle / "lessons.json").write_text(
        json.dumps({"lessons": lessons}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_narration(path: Path, what: str) -> dict:
    """Read a narration file; an absent file is simply empty prose."""
    if not path.is_file():
        return {}
    data = load_json(path, what)
    if not isinstance(data, dict):
        raise SystemExit(f"build_lesson_html.py: {what} ({path}) must contain a JSON object")
    return data


def merge_narration(dest: Path, source: Path, what: str) -> None:
    """Merge ``source`` into the narration file at ``dest`` and store the result."""
    if not source.is_file():
        raise SystemExit(f"build_lesson_html.py: narration file not found: {source}")
    if same_file(source, dest):
        return
    merged = deep_merge(read_narration(dest, what), read_narration(source, what))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_id_spec(spec: str) -> tuple[str | None, Path]:
    """Parse ``PATH`` or ``ID=PATH`` into (forced id, path)."""
    if "=" in spec:
        head, tail = spec.split("=", 1)
        if head.strip() and tail.strip() and not Path(spec).exists():
            return head.strip(), Path(tail.strip()).expanduser()
    return None, Path(spec).expanduser()


def resolve_lesson_paths(path: Path) -> tuple[Path, Path | None]:
    """Accept a lesson directory or a lesson.yaml; return (lesson.yaml, evidence.yaml).

    The evidence file is looked up next to the lesson file, first under the matching name
    (``sample-lesson.yaml`` → ``sample-evidence.yaml``) and then as plain ``evidence.yaml``.
    """
    if path.is_dir():
        lesson = path / "lesson.yaml"
        if not lesson.is_file():
            raise SystemExit(f"build_lesson_html.py: {path} に lesson.yaml がありません")
    elif path.is_file():
        lesson = path
    else:
        raise SystemExit(f"build_lesson_html.py: lesson not found: {path}")

    candidates = []
    if "lesson" in lesson.name:
        head, _, tail = lesson.name.rpartition("lesson")
        candidates.append(lesson.parent / f"{head}evidence{tail}")
    candidates.append(lesson.parent / "evidence.yaml")
    for candidate in candidates:
        if candidate.is_file():
            return lesson, candidate
    return lesson, None


def import_lessons(lessons_dir: Path, specs: list[str], warnings: list[str]) -> list[str]:
    """Copy each ``--lesson`` into ``lessons/<id>/``. Return the ids, in the order given."""
    imported: list[str] = []
    for spec in specs:
        forced_id, spec_path = parse_id_spec(spec)
        lesson_path, evidence_path = resolve_lesson_paths(spec_path)
        lesson = load_yaml(lesson_path)
        project_name = as_dict(lesson.get("project")).get("name")
        goal_title = as_dict(lesson.get("goal")).get("title")
        lesson_id = slugify(forced_id or project_name or goal_title or lesson_path.parent.name)

        dest = lessons_dir / lesson_id
        dest.mkdir(parents=True, exist_ok=True)
        copy_file(lesson_path, dest / "lesson.yaml")
        if evidence_path:
            copy_file(evidence_path, dest / "evidence.yaml")
        else:
            warnings.append(f"{lesson_path}: evidence.yaml が隣にありません（出典が空になります）")
        source_narration = lesson_path.parent / "narration.json"
        if source_narration.is_file():
            merge_narration(dest / "narration.json", source_narration, "narration file")
        imported.append(lesson_id)
    return imported


def lesson_order(bundle: Path, imported: list[str], warnings: list[str]) -> list[str]:
    """Every lesson directory in the bundle: manifest order first, then anything new."""
    lessons_dir = bundle / "lessons"
    on_disk = sorted(d.name for d in lessons_dir.iterdir()
                     if d.is_dir() and (d / "lesson.yaml").is_file())
    for directory in sorted(d.name for d in lessons_dir.iterdir() if d.is_dir()):
        if directory not in on_disk:
            warnings.append(f"lessons/{directory} に lesson.yaml がないので飛ばしました")

    order: list[str] = []
    for lesson_id in [entry["id"] for entry in load_manifest(bundle)] + imported + on_disk:
        if lesson_id in on_disk and lesson_id not in order:
            order.append(lesson_id)
    return order


def build(args: argparse.Namespace) -> tuple[Path, list[dict], list[str]]:
    bundle = Path(args.bundle).expanduser()
    lessons_dir = bundle / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    # --- bring outside material in, then take the narration overrides ---
    imported = import_lessons(lessons_dir, args.lesson or [], warnings)
    for spec in args.narration or []:
        forced_id, path = parse_id_spec(spec)
        if not forced_id:
            raise SystemExit("build_lesson_html.py: --narration needs the lesson id: "
                             "--narration ID=PATH (the main page uses --overview)")
        merge_narration(lessons_dir / forced_id / "narration.json", path, "narration file")
    if args.overview:
        merge_narration(bundle / "narration.json", Path(args.overview).expanduser(),
                        "overview narration file")

    # --- render every lesson the bundle holds (additive by construction) ---
    manifest: list[dict] = []
    for lesson_id in lesson_order(bundle, imported, warnings):
        directory = lessons_dir / lesson_id
        lesson = load_yaml(directory / "lesson.yaml")
        evidence_path = directory / "evidence.yaml"
        evidence = load_yaml(evidence_path) if evidence_path.is_file() else {}
        if not evidence_path.is_file():
            warnings.append(f"{lesson_id}: evidence.yaml がありません（出典が空になります）")
        narration = read_narration(directory / "narration.json", "narration file")
        if not narration:
            warnings.append(f"{lesson_id}: lessons/{lesson_id}/narration.json がありません"
                            "（受講者向けの文章が YAML の転記になります）")

        facts = index_facts(evidence)
        check_lesson(lesson, facts, lesson_id, warnings)
        page, summary = render_lesson_page(lesson, evidence, narration, "../../main.html",
                                           warnings, lesson_id)
        (directory / f"{lesson_id}.html").write_text(page, encoding="utf-8")
        manifest.append({"id": lesson_id,
                         "file": f"lessons/{lesson_id}/{lesson_id}.html", **summary})

    if not manifest:
        raise SystemExit(
            "build_lesson_html.py: no lessons to build. Put a lesson under "
            f"{lessons_dir}/<id>/lesson.yaml, or pass --lesson [ID=]PATH to import one."
        )

    # --- the main page ---
    title, overview_body, overview_meta, source_note = render_overview_section(
        read_narration(bundle / "narration.json", "narration file"), warnings)

    document = load_template("main.html")
    document = document.replace("__TITLE__", inline(title))
    document = document.replace("__OVERVIEW_BODY__", overview_body)
    document = document.replace("__OVERVIEW_META__", overview_meta)
    document = document.replace("__SOURCE_NOTE__", source_note)
    document = document.replace("__LESSON_CARDS__", render_lesson_cards(manifest))
    (bundle / "main.html").write_text(document, encoding="utf-8")

    write_manifest(bundle, manifest)
    return bundle, manifest, warnings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="build_lesson_html.py",
        description=(
            "Render a hands-on lesson bundle from lesson.yaml + evidence.yaml plus the "
            "narration files holding the reader-facing prose. The markup lives in "
            "templates/; this script fills it in. Every lesson directory under lessons/ is "
            "rendered on each build."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 scripts/build_lesson_html.py --bundle ./lesson-bundle\n"
            "\n"
            "  python3 scripts/build_lesson_html.py \\\n"
            "    --bundle ./lesson-bundle \\\n"
            "    --lesson spotlight=../generate-lesson-yaml/references/sample-lesson.yaml \\\n"
            "    --narration spotlight=references/sample-narration.json \\\n"
            "    --overview references/sample-overview.json\n"
        ),
    )
    parser.add_argument("--bundle", required=True,
                        help="the bundle directory (the one holding lessons/; created if missing)")
    parser.add_argument("--lesson", action="append", default=[], metavar="[ID=]PATH",
                        help="import a lesson from outside the bundle: a lesson directory "
                             "(lesson.yaml + evidence.yaml) or a lesson.yaml path. Copied into "
                             "lessons/<id>/; repeatable. Lessons already inside the bundle need "
                             "no flag")
    parser.add_argument("--narration", action="append", default=[], metavar="ID=PATH",
                        help="merge a narration JSON into lessons/<id>/narration.json: every "
                             "sentence the learner reads (lesson/step lead-ins, cautions, "
                             "checkpoint wording, Japanese gist per source); repeatable")
    parser.add_argument("--overview", metavar="PATH",
                        help="merge a narration JSON into the bundle's narration.json — "
                             "everything main.html shows (title / lead / availability / "
                             "notes / source_note)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle, manifest, warnings = build(args)

    totals = {key: 0 for key in ORIGIN_ORDER}
    for entry in manifest:
        for key, value in (entry.get("origins") or {}).items():
            totals[key] = totals.get(key, 0) + value

    print(f"build_lesson_html.py: wrote bundle {bundle.resolve()} ({len(manifest)} lesson(s))")
    for entry in manifest:
        print(f"  - {entry['id']}: {entry['title']} "
              f"({entry.get('steps', 0)} steps, {entry.get('facts', 0)} facts)"
              f"{' [truncated]' if entry.get('truncated') else ''}")
    print("  origin (author-facing, not shown in the UI): "
          + ", ".join(f"{k}={totals.get(k, 0)}" for k in ORIGIN_ORDER))
    if warnings:
        sys.stdout.flush()
        print(f"build_lesson_html.py: {len(warnings)} warning(s):", file=sys.stderr)
        for warning in warnings:
            print(f"  [warn] {warning}", file=sys.stderr)
    print("build_lesson_html.py: next, validate the bundle, e.g.:")
    print(f"  python3 scripts/validate_html.py {bundle}/main.html {bundle}/lessons/*/*.html --strict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
