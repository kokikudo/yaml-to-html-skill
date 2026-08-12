# index.yaml — the table of contents of one documentation tree

`index.yaml` records **what pages exist in a documentation tree and the path the source
publishes for each**. It is a routing map, not a copy of the documentation: it carries no page
bodies, no code, and no declarations.

## Mental model

```
Documentation tree root
   ↓ one fetch
index.yaml  ← root abstract, availability, topic groups, one entry per page with its path
```

Think of the index as **the part of a documentation site that cannot be re-derived cheaply**:

- *groups* — how the source itself partitions the tree (its own grouping, in its own order)
- *pages[].path* — transcribed from the fetched data, never guessed from a title
- *pages[].kind* — whether a page can be read on its own or only fronts other pages
- *availability* — documented platform floors, citable downstream as a real prerequisite
- *fetched_at* — for deciding when to refresh **the index itself**, nothing else

Nothing here is verified against the live site. No child page is ever fetched, so a `path` is a
faithful copy of what the source said, not a promise that it resolves today.

## Do / Don't

- ✅ Mirror the source's own group titles and group order.
- ✅ Transcribe every `path` from the URL the fetched data carries for that page.
- ❌ Do not capture page bodies, prose, code, or declarations — that happens later, per request.
- ❌ Do not build a `path` by transforming a title, or by rebuilding it from an identifier.
  Copying the source's own URL is the one rule the index exists for.
- ❌ Do not invent entries. If a fetch came back incomplete, re-fetch; do not record a guess and
  do not record an absence.
- ❌ Do not add fields that describe this skill's own process rather than the source's content,
  or that restate something already derivable from another field.

## Schema (`version: doc-index/v1`)

Fields are required unless marked *optional*.

```yaml
version: doc-index/v1

source:
  site: string           # human label, e.g. "Apple Developer Documentation"
  root_title: string     # the root page's own title
  root_path: string      # scheme-stripped, "developer.apple.com/documentation/appintents"
  root_abstract: string  # optional — the root page's own abstract, near-verbatim
  fetched_at: string     # ISO date — drives refresh decisions, nothing else
  availability:          # optional — platform floors, if the page states them
    - string

groups:
  - id: string           # stable kebab-case id
    title: string        # the source's own group title, verbatim
    abstract: string     # optional — the source's own group description, if it has one
    pages:
      - id: string       # stable kebab-case id, derived from the path tail
        title: string    # the page's own title, verbatim
        path: string     # scheme-stripped, copied from the source's own URL
        abstract: string # optional — the page's own one-line description
        kind: collection | article | symbol | sample_code | other

notes: string            # optional — free prose about how this index was built and what
                         # a reader should know before trusting it (e.g. paths that fall
                         # outside root_path and so will not update on refresh)
```

That is the whole schema. Every field except `notes` carries something read out of the source.

## Field notes

- **`path` is the whole point.** Page titles do not map to URL paths reliably. Apple's App
  Intents framework lists a page titled *"Spotlight integration"* whose path is
  `…/documentation/appintents/spotlight`, nothing like the plausible-looking
  `…/spotlight-integration` a title would suggest. Copy the URL out of the fetched data.

- **`id` stability.** Derive from the path tail, kebab-cased. Disambiguate collisions with a
  parent-segment prefix. Keep ids stable across refreshes — a later step may record a `page_id`
  that has to keep pointing at the same page.

- **`kind` is routing information.** It answers one question for a later step: *is this page
  readable on its own, or does it only front other pages?* `article` and `sample_code` carry
  their own prose; `symbol` is an API reference entry; `collection` is a landing page whose
  children the later step will have to fetch separately, since the index stores no children of
  its own. It is a fact about the page, not a judgement about its usefulness. Map the source's own
  metadata onto these values rather than inferring from the title. For Apple's JSON, the
  `kind`/`role` pair: `article`/`collectionGroup` → `collection`, `article`/`article` →
  `article`, `article`/`sampleCode` → `sample_code`, `symbol`/* → `symbol`, except a framework
  landing page (`symbol`/`collection`) → `collection`.

- **A page's `path` may fall outside `root_path`.** Documentation trees link neighbouring trees
  into their topic groups — App Intents lists two AppIntentsTesting pages and an Updates page.
  This is not an error and needs no flag: refresh logic can compare `path` against `root_path`
  when it needs to know, and a stored copy of that comparison could only go stale.

- **`abstract` may be rough.** It exists to route a request to candidate pages. Precision is
  spent downstream, on verbatim capture of the few pages actually used.

## A note on URLs (offline safety)

Strip the `http(s)://` scheme from every `path`. Index paths get copied downstream and can end
up inside an offline, self-contained HTML bundle, where `validate_html.py --strict` flags any
URL scheme. Establishing the habit here prevents a failure two stages later.

## Minimal example

```yaml
version: doc-index/v1
source:
  site: "Apple Developer Documentation"
  root_title: "App Intents"
  root_path: "developer.apple.com/documentation/appintents"
  fetched_at: "2026-08-12"
groups:
  - id: feature-integration
    title: "Feature integration"
    pages:
      - id: spotlight
        title: "Spotlight integration"
        path: "developer.apple.com/documentation/appintents/spotlight"
        abstract: "Add your entities to your app's Spotlight index, and automate the indexing of your content"
        kind: collection
```

See `sample-index.yaml` for a fuller, working example.
