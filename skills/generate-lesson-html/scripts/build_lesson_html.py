#!/usr/bin/env python3
"""build_lesson_html.py

Render a hands-on **lesson bundle** from ``index.yaml`` (doc-index/v1), one or more
``lesson.yaml`` / ``evidence.yaml`` pairs (lesson/v1 + evidence/v1), and a **copy file**
(``--copy``) holding the reader-facing Japanese prose.

Two kinds of input, on purpose
------------------------------
``lesson.yaml`` is a *record*: what to build, in what order, with what evidence. Rendered
verbatim it reads like a spec, not like teaching material. So the page takes:

- **from the YAML** — titles, file paths, source code, requirements, checkpoints, sources;
- **from the copy file** — every explanatory sentence the learner reads (course lead-in,
  per-step lead-in, per-file explanation, cautions, checkpoint wording, and the Japanese
  gist of each quoted source).

Author metadata (``origin``, ``origin_note``, ``needs_facts``, fact ids, YAML file names)
stays out of the learner-facing UI. The origin rules are still *checked* — violations are
reported as build warnings for the author.

The markup itself lives in ``templates/`` and is the single source of truth for layout:

    templates/index.html    the course list  (概要 + コース + コース追加プロンプト)
    templates/course.html   one course       (left: Step nav / right: the current Step)

What it produces
----------------

    <bundle>/
      index.html               course list; links to views/<course>.html
      courses.json             ordered manifest: {"courses":[{id,title,file,...}, ...]}
      copy.json                the merged reader-facing prose (reused on later builds)
      prompts.json             copied in (the "add a course" templates)
      index.yaml               copied in (its absolute path is cited by the prompts)
      courses/<course>/lesson.yaml
      courses/<course>/evidence.yaml
      views/<course>.html      one full page per course

There is **no iframe**: a course is a normal page reached by a link, and the back link
returns to the list. That keeps the bundle openable in any browser over ``file://``.

Courses are **additive**. Re-running with one new ``--lesson`` appends a course and leaves
the existing ones untouched; re-running with an existing course id updates that course.

Placeholder substitution (paths, not content)
----------------------------------------------
Prompt strings in ``prompts.json`` may contain ``{{index_yaml_path}}``,
``{{bundle_dir}}``, ``{{courses_dir}}``, ``{{lesson_yaml_paths}}``, ``{{copy_json_path}}``
and ``{{build_script_path}}``. They are replaced with absolute paths so a
local-file-reading AI can open them. YAML *content* is never embedded in a prompt.

Example
-------
    python3 scripts/build_lesson_html.py \
      --bundle ./lesson-bundle \
      --index /abs/path/index.yaml \
      --lesson /abs/path/lessons/spotlight \
      --copy /abs/path/copy.json \
      --prompts references/sample-prompts.json
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

    Type names, API names and file names are wrapped in backticks by the copy author so
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
    return s.strip("-_") or "course"


def as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def fill_placeholders(text: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def deep_merge(base: dict, overlay: dict) -> dict:
    """Merge ``overlay`` into ``base`` (dicts recurse, everything else is replaced)."""
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


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
    return f'<p class="ref-line">{esc(label)}: {"、".join(links)}</p>'


# ---------------------------------------------------------------------------
# course page rendering
# ---------------------------------------------------------------------------

def render_overview_panel(lesson: dict, facts: dict[str, dict], copy: dict,
                          missing: list[str], warnings: list[str], course_id: str) -> str:
    goal = as_dict(lesson.get("goal"))
    project = as_dict(lesson.get("project"))
    scope = as_dict(lesson.get("scope"))
    parts: list[str] = ['<article class="panel" id="panel-overview">',
                        f'  <h2>{inline(goal.get("title") or "概要")}</h2>']

    if scope.get("truncated"):
        reason = copy.get("truncated_note") or scope.get("truncated_reason")
        parts.append(
            '  <div class="banner"><strong>このコースは途中までです。</strong> '
            f'{inline(reason)}</div>'
        )

    lead = copy.get("lead")
    if not lead:
        warnings.append(f"{course_id}: copy に lead がありません（概要が YAML の転記になります）")
    parts.append(prose(lead or goal.get("outcome"), "lead"))

    goal_text = copy.get("goal") or goal.get("outcome")
    if goal_text:
        parts.append('  <h3>このコースを終えたときの状態</h3>')
        parts.append(prose(goal_text))

    chips = []
    if project.get("stack"):
        chips.append(f'<span class="chip">{inline(project["stack"])}</span>')
    chips.append(f'<span class="chip">全 {len(as_list(lesson.get("steps")))} 手順</span>')
    parts.append(f'  <div class="chips">{"".join(chips)}</div>')

    requirements = [r for r in as_list(project.get("requirements")) if isinstance(r, dict)]
    if requirements or copy.get("requirements"):
        parts.append("  <h3>始める前に必要なもの</h3>")
        if copy.get("requirements_lead"):
            parts.append(prose(copy["requirements_lead"]))
        parts.append('  <ul class="plain-list">')
        rewritten = as_list(copy.get("requirements"))
        for position, requirement in enumerate(requirements):
            text = rewritten[position] if position < len(rewritten) else requirement.get("text")
            refs = fact_links(requirement.get("source_refs"), facts, missing, "出典")
            parts.append(f"    <li>{inline(text)}{refs}</li>")
        for extra in rewritten[len(requirements):]:
            parts.append(f"    <li>{inline(extra)}</li>")
        parts.append("  </ul>")

    scaffold_steps = as_list(copy.get("scaffold")) or \
        as_list(as_dict(project.get("scaffold")).get("steps"))
    if scaffold_steps:
        parts.append("  <h3>下ごしらえ（プロジェクトの用意）</h3>")
        if copy.get("scaffold_lead"):
            parts.append(prose(copy["scaffold_lead"]))
        parts.append("  <ol>" + "".join(f"<li>{inline(s)}</li>" for s in scaffold_steps) + "</ol>")

    covers = as_list(copy.get("covers")) or as_list(scope.get("covers"))
    excludes = as_list(copy.get("excludes")) or as_list(scope.get("excludes"))
    if covers or excludes:
        parts.append("  <h3>このコースで扱うこと</h3>")
        if covers:
            parts.append("  <ul>" + "".join(f"<li>{inline(c)}</li>" for c in covers) + "</ul>")
        if excludes:
            parts.append('  <p class="muted">扱わないこと</p>')
            parts.append("  <ul>" + "".join(f"<li>{inline(x)}</li>" for x in excludes) + "</ul>")

    for note in as_list(copy.get("notes")):
        parts.append(f'  <div class="note">{inline(note)}</div>')

    parts.append("</article>")
    return "\n".join(p for p in parts if p)


def render_step_panel(step: dict, number: int, total: int, facts: dict[str, dict],
                      copy: dict, missing: list[str], warnings: list[str],
                      course_id: str) -> str:
    step_id = str(step.get("id") or f"step-{number}")
    parts: list[str] = [f'<article class="panel hidden" id="panel-{esc(step_id)}">',
                        f'  <p class="eyebrow">Step {number} / {total}</p>',
                        f'  <h2>{inline(step.get("title") or step_id)}</h2>']

    lead = copy.get("lead")
    if not lead:
        warnings.append(f"{course_id}/{step_id}: copy に lead がありません"
                        "（導入文が YAML の転記になります）")
    parts.append(f'  <div class="lead-box">{prose(lead or step.get("why"))}</div>')

    files = [f for f in as_list(step.get("files")) if isinstance(f, dict)]
    file_copy = as_dict(copy.get("files"))
    all_refs: list[str] = []
    if files:
        parts.append("  <h3>書くコード</h3>")
    for position, file_item in enumerate(files, start=1):
        code_id = f"code-{slugify(step_id)}-{position}"
        path = str(file_item.get("path", ""))
        action_label = ACTION_LABELS.get(str(file_item.get("action", "")), "")
        lang = file_item.get("lang")
        all_refs.extend(str(r) for r in as_list(file_item.get("source_refs")) if r)
        explanation = file_copy.get(path) or file_copy.get(Path(path).name)
        parts.append('  <div class="file">')
        parts.append('    <div class="file-head">')
        parts.append(f'      <code class="file-path">{esc(path)}</code>')
        parts.append('      <span class="file-meta">')
        if action_label:
            parts.append(f'        <span class="badge neutral">{esc(action_label)}</span>')
        if lang:
            parts.append(f'        <span class="badge neutral">{esc(lang)}</span>')
        parts.append(f'        <button class="copy-btn" type="button" data-target="{code_id}">'
                     "コードをコピー</button>")
        parts.append("      </span>")
        parts.append("    </div>")
        if explanation:
            parts.append(f'    <div class="file-note">{prose(explanation)}</div>')
        parts.append(f'    <pre class="code" id="{code_id}">{esc(file_item.get("content", ""))}</pre>')
        parts.append("  </div>")

    for note in as_list(copy.get("notes")):
        parts.append(f'  <div class="note">{inline(note)}</div>')

    checkpoint = as_dict(step.get("checkpoint"))
    if checkpoint:
        kind = str(checkpoint.get("kind", ""))
        label, meaning = CHECKPOINT_LABELS.get(kind, ("確認", ""))
        all_refs.extend(str(r) for r in as_list(checkpoint.get("source_refs")) if r)
        parts.append("  <h3>ここまでの確認</h3>")
        parts.append('  <div class="checkpoint">')
        parts.append(f'    <span class="badge check" title="{esc(meaning)}">{esc(label)}</span>')
        parts.append(prose(copy.get("checkpoint") or checkpoint.get("expect"), "expect"))
        parts.append("  </div>")

    errors = [e for e in as_list(step.get("common_errors")) if isinstance(e, dict)]
    if errors:
        parts.append("  <h3>つまずいたときは</h3>")
        for error in errors:
            ref = error.get("source_ref")
            if ref:
                all_refs.append(str(ref))
            parts.append('  <div class="errors">')
            parts.append(f'    <p class="symptom">{inline(error.get("symptom"))}</p>')
            parts.append(f'    <p class="cause">{inline(error.get("cause"))}</p>')
            parts.append(fact_links([ref] if ref else [], facts, missing, "出典"))
            parts.append("  </div>")

    unique_refs = list(dict.fromkeys(all_refs))
    see_also = [s for s in as_list(step.get("see_also")) if isinstance(s, dict)]
    if unique_refs or see_also:
        parts.append("  <h3>この手順のもとになった資料</h3>")
    if unique_refs:
        parts.append(fact_links(unique_refs, facts, missing, "出典"))
    if see_also:
        parts.append('  <ul class="see-also">')
        for link in see_also:
            parts.append(f'    <li>{inline(link.get("title"))}'
                         f'<br><span class="path">{esc(link.get("path"))}</span></li>')
        parts.append("  </ul>")

    parts.append("</article>")
    return "\n".join(p for p in parts if p)


def render_evidence_panel(lesson: dict, facts: dict[str, dict], copy: dict,
                          warnings: list[str], course_id: str) -> str:
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

    gists = as_dict(copy.get("facts"))
    parts = ['<article class="panel hidden" id="panel-evidence">',
             "  <h2>出典一覧</h2>",
             prose(copy.get("lead") or
                   "このコースの説明とコードが、公式ドキュメントのどの記述に基づいているかの"
                   "一覧です。各手順の「この手順のもとになった資料」から、ここへ飛べます。")]
    if not facts:
        parts.append('  <p class="muted">出典が登録されていません。</p>')

    for fact_id, fact in facts.items():
        source = as_dict(fact.get("source"))
        gist = gists.get(fact_id)
        if not gist:
            warnings.append(f"{course_id}: copy.facts に '{fact_id}' の日本語要旨がありません")
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


def render_course_page(lesson: dict, evidence: dict, copy: dict, back_href: str,
                       warnings: list[str], course_id: str) -> tuple[str, dict]:
    """Render one views/<course>.html; return (html, summary)."""
    template = load_template("course.html")
    facts = index_facts(evidence)
    missing: list[str] = []

    goal = as_dict(lesson.get("goal"))
    steps = [s for s in as_list(lesson.get("steps")) if isinstance(s, dict)]
    step_copy = as_dict(copy.get("steps"))

    nav_items: list[tuple[str, str, str]] = [("overview", "概", "コースの概要")]
    panels = [render_overview_panel(lesson, facts, copy, missing, warnings, course_id)]
    for number, step in enumerate(steps, start=1):
        step_id = str(step.get("id") or f"step-{number}")
        nav_items.append((step_id, str(number), str(step.get("title") or step_id)))
        panels.append(render_step_panel(step, number, len(steps), facts,
                                        as_dict(step_copy.get(step_id)), missing,
                                        warnings, course_id))
    nav_items.append(("evidence", "典", "出典一覧"))
    panels.append(render_evidence_panel(lesson, facts, as_dict(copy.get("evidence")),
                                        warnings, course_id))

    for ref in dict.fromkeys(missing):
        warnings.append(f"{course_id}: source_ref '{ref}' が evidence.yaml に見つかりません")

    document = template
    document = document.replace("__COURSE_TITLE__", inline(goal.get("title") or course_id))
    document = document.replace("__BACK_HREF__", esc(back_href))
    document = document.replace("__STEP_COUNT__", str(len(steps)))
    document = document.replace("__NAV_ITEMS__", render_nav(nav_items))
    document = document.replace("__PANELS__", "\n".join(panels))

    summary = {
        "title": str(goal.get("title") or course_id),
        "summary": str(copy.get("summary") or goal.get("outcome") or ""),
        "stack": str(as_dict(lesson.get("project")).get("stack") or ""),
        "steps": len(steps),
        "facts": len(facts),
        "origins": count_origins(lesson),
        "truncated": bool(as_dict(lesson.get("scope")).get("truncated")),
    }
    return document, summary


# ---------------------------------------------------------------------------
# index page rendering
# ---------------------------------------------------------------------------

def render_overview_section(index_data: dict | None, copy: dict,
                            warnings: list[str]) -> tuple[str, str, str, str]:
    """Return (page title, overview body, meta chips, closing note)."""
    source = as_dict((index_data or {}).get("source"))
    title = str(copy.get("title") or source.get("root_title") or "ハンズオン教材")

    lead = copy.get("lead")
    if lead:
        body = prose(lead)
    else:
        warnings.append("copy.overview.lead がありません（コース一覧の概要が空になります）")
        body = ('<p class="empty">このコース一覧の概要はまだ書かれていません。'
                '--copy に overview.lead を渡してください。</p>')
    for note in as_list(copy.get("notes")):
        body += f'\n<div class="note">{inline(note)}</div>'

    chips = [f'<span class="chip">{esc(a)}</span>' for a in as_list(source.get("availability"))]
    meta = f'<div class="chips">{"".join(chips)}</div>' if chips else ""

    note = ""
    if copy.get("source_note"):
        note = f'<p class="source-note">{inline(copy["source_note"])}</p>'
    elif source.get("site"):
        note = (f'<p class="source-note">出典: {esc(source["site"])}'
                f'{" / " + esc(source["root_path"]) if source.get("root_path") else ""}</p>')
    return (title, body, meta, note)


def render_course_cards(courses: list[dict]) -> str:
    if not courses:
        return '<p class="empty">コースがまだありません。</p>'
    cards = []
    for course in courses:
        chips = [f'<span class="chip">全 {course.get("steps", 0)} 手順</span>']
        if course.get("stack"):
            chips.append(f'<span class="chip">{esc(course["stack"])}</span>')
        if course.get("truncated"):
            chips.append('<span class="chip warn">途中まで</span>')
        cards.append("\n".join([
            f'<a class="course-card" href="views/{esc(course["file"])}">',
            f'  <h3>{inline(course["title"])}</h3>',
            f'  <p class="outcome">{inline(course.get("summary", ""))}</p>',
            f'  <div class="chips">{"".join(chips)}</div>',
            '  <span class="course-cta">はじめる →</span>',
            "</a>",
        ]))
    return "\n".join(cards)


def render_prompt_cards(prompts: list, mapping: dict[str, str]) -> str:
    if not prompts:
        return '<p class="empty">プロンプトテンプレートがありません。</p>'
    cards = []
    for position, item in enumerate(prompts):
        if not isinstance(item, dict):
            raise SystemExit("build_lesson_html.py: each prompt entry must be a JSON object")
        pid = str(item.get("id", f"prompt-{position}"))
        dom_id = "prompt-" + "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in pid)
        tags = item.get("tags") or []
        tags_html = ""
        if isinstance(tags, list) and tags:
            chips = "".join(f'<span class="tag">{esc(t)}</span>' for t in tags)
            tags_html = f'<div class="tags">{chips}</div>'
        body = fill_placeholders(str(item.get("prompt", "")), mapping)
        cards.append("\n".join([
            '<article class="card">',
            '  <div class="card-head">',
            f'    <h3>{esc(item.get("title", pid))}</h3>',
            f"    {tags_html}",
            "  </div>",
            f'  <p class="card-desc">{esc(item.get("description", ""))}</p>',
            '  <details class="prompt-details">',
            "    <summary>プロンプト本文を表示 / 折りたたみ</summary>",
            f'    <pre class="prompt-body" id="{dom_id}">{esc(body)}</pre>',
            "  </details>",
            f'  <button class="copy-btn" type="button" data-target="{dom_id}">'
            "プロンプトをコピー</button>",
            "</article>",
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


def check_lesson(lesson: dict, facts: dict[str, dict], course_id: str,
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
            warnings.append(f"{course_id}/{where}: 未知の origin '{origin}'")
            return
        if origin == "verbatim_from_doc" and not refs:
            warnings.append(f"{course_id}/{where}: verbatim_from_doc に source_refs がありません")
        if origin == "adapted" and (not refs or not note):
            warnings.append(f"{course_id}/{where}: adapted は source_refs 1 件以上と origin_note が必要です")
        if origin == "synthesized" and (len(refs) < 2 or not note):
            warnings.append(f"{course_id}/{where}: synthesized は source_refs 2 件以上と origin_note が必要です")
        if origin == "authored" and (refs or not note):
            warnings.append(f"{course_id}/{where}: authored は source_refs 空 + origin_note 必須です")

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
            warnings.append(f"{course_id}: step id '{step_id}' が重複しています")
        seen_ids.add(step_id)
        for position, file_item in enumerate(as_list(step.get("files")), start=1):
            audit(file_item, f"{step_id}.files[{position}]")
        audit(step.get("checkpoint"), f"{step_id}.checkpoint")
        for error in as_list(step.get("common_errors")):
            if isinstance(error, dict):
                if not error.get("source_ref"):
                    warnings.append(f"{course_id}/{step_id}: common_errors に source_ref がありません")
                else:
                    used.add(str(error["source_ref"]))

    for fact_id in facts:
        if fact_id not in used:
            warnings.append(f"{course_id}: fact '{fact_id}' がどこからも参照されていません")


# ---------------------------------------------------------------------------
# bundle assembly
# ---------------------------------------------------------------------------

def load_manifest(bundle: Path) -> list[dict]:
    path = bundle / "courses.json"
    if not path.is_file():
        return []
    data = load_json(path, "courses.json")
    courses = data.get("courses") if isinstance(data, dict) else None
    if not isinstance(courses, list):
        return []
    return [c for c in courses if isinstance(c, dict) and c.get("id")]


def write_manifest(bundle: Path, courses: list[dict]) -> None:
    (bundle / "courses.json").write_text(
        json.dumps({"courses": courses}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_copy(bundle: Path, copy_arg: str | None) -> dict:
    """Merge the passed copy file into whatever the bundle already holds, and store it."""
    stored: dict = {}
    dest = bundle / "copy.json"
    if dest.is_file():
        data = load_json(dest, "copy.json")
        stored = data if isinstance(data, dict) else {}
    if copy_arg:
        data = load_json(copy_arg, "copy file")
        if not isinstance(data, dict):
            raise SystemExit("build_lesson_html.py: the copy file must contain a JSON object")
        stored = deep_merge(stored, data)
        dest.write_text(json.dumps(stored, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return stored


def parse_lesson_specs(specs: list[str]) -> list[tuple[str | None, Path]]:
    """Parse ``--lesson PATH`` or ``--lesson NAME=PATH`` into (forced id, path) pairs."""
    pairs: list[tuple[str | None, Path]] = []
    for spec in specs:
        name: str | None = None
        raw = spec
        if "=" in spec:
            head, tail = spec.split("=", 1)
            if head.strip() and tail.strip() and not Path(spec).exists():
                name, raw = head.strip(), tail.strip()
        pairs.append((name, Path(raw).expanduser()))
    return pairs


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


def build(args: argparse.Namespace) -> tuple[Path, list[dict], list[str]]:
    bundle = Path(args.bundle).expanduser()
    (bundle / "views").mkdir(parents=True, exist_ok=True)
    (bundle / "courses").mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    manifest = load_manifest(bundle)
    copy = load_copy(bundle, args.copy)
    course_copy = as_dict(copy.get("courses"))

    # --- courses (additive: append new, update existing in place) ---
    for forced_name, spec_path in parse_lesson_specs(args.lesson or []):
        lesson_path, evidence_path = resolve_lesson_paths(spec_path)
        lesson = load_yaml(lesson_path)
        evidence = load_yaml(evidence_path) if evidence_path else {}
        if evidence_path is None:
            warnings.append(f"{lesson_path}: evidence.yaml が隣にありません（出典が空になります）")

        project_name = as_dict(lesson.get("project")).get("name")
        goal_title = as_dict(lesson.get("goal")).get("title")
        course_id = slugify(forced_name or project_name or goal_title or lesson_path.parent.name)
        this_copy = as_dict(course_copy.get(course_id))
        if not this_copy:
            warnings.append(f"{course_id}: copy.courses['{course_id}'] がありません"
                            "（受講者向けの文章が YAML の転記になります）")

        facts = index_facts(evidence)
        check_lesson(lesson, facts, course_id, warnings)
        page, summary = render_course_page(lesson, evidence, this_copy, "../index.html",
                                           warnings, course_id)

        (bundle / "views" / f"{course_id}.html").write_text(page, encoding="utf-8")
        course_dir = bundle / "courses" / course_id
        course_dir.mkdir(parents=True, exist_ok=True)
        (course_dir / "lesson.yaml").write_text(read_text(lesson_path), encoding="utf-8")
        if evidence_path:
            (course_dir / "evidence.yaml").write_text(read_text(evidence_path), encoding="utf-8")

        entry = {"id": course_id, "file": f"{course_id}.html", **summary}
        existing = next((c for c in manifest if c["id"] == course_id), None)
        if existing is None:
            manifest.append(entry)
        else:
            existing.update(entry)

    if not manifest:
        raise SystemExit(
            "build_lesson_html.py: no courses to build. Pass at least one --lesson PATH "
            "(or build into a bundle that already has courses.json)."
        )
    for course in manifest:
        if not (bundle / "views" / course["file"]).is_file():
            warnings.append(f"courses.json が参照する views/{course['file']} がありません")

    # --- the index page ---
    index_data = None
    index_dest = bundle / "index.yaml"
    if args.index:
        index_dest.write_text(read_text(args.index), encoding="utf-8")
    if index_dest.is_file():
        index_data = load_yaml(index_dest)

    prompts_dest = bundle / "prompts.json"
    if args.prompts:
        prompts_dest.write_text(read_text(args.prompts), encoding="utf-8")
    prompts: list = []
    if prompts_dest.is_file():
        data = load_json(prompts_dest, "prompts.json")
        if not isinstance(data, list):
            raise SystemExit("build_lesson_html.py: prompts file must contain a JSON array")
        prompts = data

    lesson_paths = "\n".join(
        f"- {c['title']}: {(bundle / 'courses' / c['id'] / 'lesson.yaml').resolve()}"
        for c in manifest
    )
    mapping = {
        "index_yaml_path": str(index_dest.resolve()) if index_dest.is_file() else "(index.yaml は未指定)",
        "bundle_dir": str(bundle.resolve()),
        "courses_dir": str((bundle / "courses").resolve()),
        "lesson_yaml_paths": lesson_paths or "(コースがありません)",
        "copy_json_path": str((bundle / "copy.json").resolve()),
        "build_script_path": str(Path(__file__).resolve()),
    }

    title, overview_body, overview_meta, source_note = render_overview_section(
        index_data, as_dict(copy.get("overview")), warnings)
    if args.title:
        title = args.title

    document = load_template("index.html")
    document = document.replace("__TITLE__", inline(title))
    document = document.replace("__OVERVIEW_BODY__", overview_body)
    document = document.replace("__OVERVIEW_META__", overview_meta)
    document = document.replace("__SOURCE_NOTE__", source_note)
    document = document.replace("__COURSE_CARDS__", render_course_cards(manifest))
    document = document.replace("__PROMPT_CARDS__", render_prompt_cards(prompts, mapping))
    (bundle / "index.html").write_text(document, encoding="utf-8")

    write_manifest(bundle, manifest)
    return bundle, manifest, warnings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="build_lesson_html.py",
        description=(
            "Render a hands-on lesson bundle from index.yaml + lesson.yaml/evidence.yaml "
            "plus a copy file holding the reader-facing prose. The markup lives in "
            "templates/; this script fills it in. A new --lesson appends a course."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "example:\n"
            "  python3 scripts/build_lesson_html.py \\\n"
            "    --bundle ./lesson-bundle \\\n"
            "    --index ../generate-doc-index/references/sample-index.yaml \\\n"
            "    --lesson ../generate-lesson-yaml/references/sample-lesson.yaml \\\n"
            "    --copy references/sample-copy.json \\\n"
            "    --prompts references/sample-prompts.json\n"
        ),
    )
    parser.add_argument("--bundle", required=True, help="output bundle directory (created if missing)")
    parser.add_argument("--lesson", action="append", default=[], metavar="[NAME=]PATH",
                        help="a course: a lesson directory (lesson.yaml + evidence.yaml) or a "
                             "lesson.yaml path; repeatable, appends/updates each run")
    parser.add_argument("--copy", help="path to the copy JSON: every sentence the learner "
                                       "reads (course/step lead-ins, cautions, checkpoint "
                                       "wording, Japanese gist per source). Merged into the "
                                       "bundle's copy.json and reused when omitted")
    parser.add_argument("--index", help="path to index.yaml (doc-index/v1); supplies the "
                                        "availability chips and is cited by the prompts")
    parser.add_argument("--prompts", help="path to prompts.json (the 'add a course' templates); "
                                          "reused from the bundle when omitted")
    parser.add_argument("--title", help="optional override for the course-list title")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle, manifest, warnings = build(args)

    totals = {key: 0 for key in ORIGIN_ORDER}
    for course in manifest:
        for key, value in (course.get("origins") or {}).items():
            totals[key] = totals.get(key, 0) + value

    print(f"build_lesson_html.py: wrote bundle {bundle.resolve()} ({len(manifest)} course(s))")
    for course in manifest:
        print(f"  - {course['id']}: {course['title']} "
              f"({course.get('steps', 0)} steps, {course.get('facts', 0)} facts)"
              f"{' [truncated]' if course.get('truncated') else ''}")
    print("  origin (author-facing, not shown in the UI): "
          + ", ".join(f"{k}={totals.get(k, 0)}" for k in ORIGIN_ORDER))
    if warnings:
        sys.stdout.flush()
        print(f"build_lesson_html.py: {len(warnings)} warning(s):", file=sys.stderr)
        for warning in warnings:
            print(f"  [warn] {warning}", file=sys.stderr)
    print("build_lesson_html.py: next, validate the bundle, e.g.:")
    print(f"  python3 scripts/validate_html.py {bundle}/index.html {bundle}/views/*.html --strict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
