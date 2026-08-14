---
name: generate-doc-index
description: capture the table of contents of one documentation tree (currently Apple Developer Documentation) in a single fetch as a reusable doc-index/v1 index.yaml — root abstract, platform availability, and topic groups mirroring the site's own grouping, with one entry per child page carrying the path the source itself publishes for it, plus its abstract and kind. captures no page bodies: the index exists so a later step can route a user's request to the right pages and then fetch those pages by their recorded path instead of guessing slugs. use when the user wants a cheap, durable map of a documentation tree before generating reader-tailored material from it, or wants to refresh an existing index.
---

# generate-doc-index

Capture **what pages exist** in one documentation tree, and **the path the source publishes for
each**, in a single fetch. The result is `index.yaml` — a routing map, not a copy of the
documentation.

```
Documentation tree root
  ↓ one fetch (this skill)
index.yaml   (root abstract, availability, topic groups, one entry per page with its path)
  ↓ read by a later generation step
  ↓ that step fetches only the few pages the user's request actually needs
reader-tailored material (explainer / hands-on / whatever the downstream skill builds)
```

The index deliberately holds **no page bodies**. What it adds is the part that cannot be
re-derived cheaply: the set of pages that exist, and the path the source publishes for each.

## Why the recorded path matters

The index's main practical job is to stop a later step from **guessing slugs**. Page titles do
not map to URL paths reliably — Apple lists a page titled "Spotlight integration" that lives at
`…/appintents/spotlight`, not at the plausible-looking `…/appintents/spotlight-integration`.

So every `path` is **transcribed from the URL the source's own data carries for that page**.
This skill never turns a title into a path. It also never fetches a child page, so it does not
verify that a recorded path resolves — the guarantee is fidelity to the source, not liveness.

## What this skill does

- **Generate** a new `index.yaml` from one documentation tree root, in a single fetch.
- **Refresh** an existing index when the source documentation has changed.
- **Does not** capture page bodies, code, or declarations — a later step fetches those per
  request, transiently.
- **Does not** go deeper than the root's direct children. Deeper pages are reached transiently
  at generation time, so the index has no expand mode and stores no nested children.
- **Does not** interpret or compress meaning, and does not produce HTML.

## The index is read-only during material generation

A downstream generation step **reads** `index.yaml` and never writes to it. When it needs a page
that the index does not list, it fetches that page's parent transiently to locate the child, and
uses it — without writing anything back.

This matters because the index is shared, persistent state. If generation silently rewrote it,
the same request would produce different material depending on what an unrelated earlier session
happened to add, and nothing would record why. The index changes only when a user asks this
skill to refresh it.

## Output bundle structure

Create a directory with the correct name based on the source content, and place the generated
`index.yaml` inside it.

```
<bundle>/
  index.yaml
```

**Do not write into this plugin's own repository** unless the user is specifically working on
this plugin; a generated index is unrelated content that would pollute `git status` here.

Report the **absolute path** at the end so a future session can point straight at it.

## Steps

1. **Identify the tree root.** Take the documentation root URL the user gave. If they gave a
   deep page instead of a root, confirm which level they want indexed before fetching.

2. **Normalize to the data endpoint (Apple).** Apple documentation pages render via JavaScript,
   so fetching the rendered URL returns little more than a title. Fetch the JSON data endpoint
   instead:

   ```
   developer.apple.com/documentation/<path>
     → developer.apple.com/tutorials/data/documentation/<path>.json
   ```

   This skill currently supports **Apple Developer Documentation only** — for any other site,
   tell the user it is not yet supported rather than guessing at an equivalent endpoint.

3. **Extract the root's own metadata.** Title, abstract, and — when the page states it —
   platform availability. Availability is worth carrying: a downstream hands-on can cite it as a
   documented prerequisite instead of inventing one.

4. **Extract the topic groups.** Mirror the site's own grouping (Apple exposes these as
   `topicSections`). Preserve the source's group order and group titles; do not re-organize them
   into a structure you think is better. The grouping is itself information about how the
   framework's authors partition it.

5. **Transcribe each child page's path from the data, never from its title.** A group lists its
   members as `identifiers`; the document's top-level `references` map turns each identifier
   into that page's title, abstract, and URL. Copy the URL as given — do not rebuild a path out
   of the identifier, which silently breaks for pages that live in a neighbouring tree. See
   "Reading Apple's JSON" below for the exact field names.

   **A summarizing fetch may silently drop the `identifiers` arrays** — they are long and look
   like noise, so a summarizer tends to keep a group's title and abstract and discard its
   membership. A group that comes back with no identifiers is a failed read, not an empty group:
   re-fetch, asking explicitly for the literal `identifiers` arrays and `references` entries,
   and keep going until every group's entries are resolved. Never record a group as empty on the
   strength of one incomplete read, and never fill the gap with a guessed path.

6. **Classify each page's `kind`.** `collection` (a page whose purpose is to group others),
   `article` (prose or a guide), `symbol` (an API type/protocol/function), `sample_code`, or
   `other`. This is routing information for a later step: it says whether a page can be read
   directly, or whether it fronts other pages that may need to be reached.

7. **Stay at depth 1.** One fetch, the root's direct children. Do not recurse. A downstream step
   reaches deeper pages transiently when it needs them, so completeness is not the index's job.

8. **Refresh mode.** Re-fetch the root, update titles/abstracts/paths and `fetched_at`, and
   report what changed — especially pages that disappeared, since anything pointing at them
   downstream is now stale. Keep every surviving `id` stable.

9. **Report the absolute path**, plus the group and page counts.

## Notes

- **Never guess a path from a title.** This is the single rule the index exists to enforce.
- **Strip `http(s)://` from every path.** Index paths get copied downstream and can end up in an
  offline HTML bundle, where a validator flags any URL scheme. Establishing the habit here
  prevents a failure two stages later.
- **Never invent an entry, and never record an absence you have not confirmed.** Both mislead.
  A group whose entries did not come back is a read to retry, not a finding to write down.
- **Keep the schema small.** Before adding a field, ask whether it carries something read out of
  the source or merely describes how this skill happened to run. The second kind has to justify
  itself.
- **Abstracts are for routing, and may be rough.** They exist so a later step can match a user's
  request to candidate pages. Precision is spent downstream, on the verbatim capture of the few
  pages actually used — not here.

## Reading Apple's JSON

The table of contents is split across two places, and one index entry is a join of both.

`topicSections[]` gives a group's title and its membership as opaque identifiers — no titles,
no URLs:

```jsonc
"topicSections": [
  { "title": "Feature integration",
    "identifiers": ["doc://com.apple.AppIntents/documentation/AppIntents/Spotlight", "…"] }
]
```

The top-level `references` map, keyed by those identifiers, carries the content:

```jsonc
"references": {
  "doc://com.apple.AppIntents/documentation/AppIntents/Spotlight": {
    "title": "Spotlight integration",
    "url": "/documentation/appintents/spotlight",   // ← the path, verbatim
    "abstract": [{ "type": "text", "text": "Add your entities to your app's…" }],
    "kind": "article", "role": "collectionGroup"
  }
}
```

`url` is root-relative, so the recorded `path` is the site host plus that value:
`developer.apple.com` + `/documentation/appintents/spotlight`.

Take `url` as it stands. Reconstructing it from the identifier (lowercase the last segment,
append to `root_path`) happens to work for same-tree pages and quietly produces a wrong path for
the rest — App Intents links out to `/documentation/updates/appintents` and to two
`/documentation/appintentstesting/…` pages, none of which sit under the root.

## Reference material

- `references/doc-index-yaml-schema.md` — the index schema (`doc-index/v1`)
- `references/sample-index.yaml` — a worked index (Apple's App Intents framework)
