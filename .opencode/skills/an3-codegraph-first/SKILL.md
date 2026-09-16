---
name: an3-codegraph-first
description: Use at the start of any AN3/Vibe Coded Emulator code investigation or edit to query the CodeGraph index before grep/glob/read, pass the correct projectPath, and re-index when the index is stale. Triggers on "find where", "how does X work", "who calls", "blast radius", "codegraph", "index stale".
---

# CodeGraph first

This repo has a `.codegraph/` index (`codegraph` 1.6.0). Before any grep, glob,
or read of source, get the relevant symbols and the call paths between them in
one call.

## Query

Prefer the MCP tool with an explicit project path:

```
codegraph_explore(query="<symbols or question>", projectPath="/Users/meomeo/Documents/edit an3tocom apps&web")
```

The same query works as a bag of symbols, a file name, or a natural-language
question. One focused explore returns verbatim, line-numbered source plus the
call path and a blast-radius summary — treat that source as already read and do
not re-open those files.

If the MCP server is unavailable, use the shell:

```bash
codegraph explore "<symbols/question>" --path "/Users/meomeo/Documents/edit an3tocom apps&web"
```

## After a query

- Read only the files the result narrows down; use `Read` for the exact lines.
- Re-check with CodeGraph before every edit to see callers/callees and blast
  radius.
- Skip CodeGraph only for content genuinely outside the index (config, CSS,
  HTML/text strings, generated assets, binary artifacts) and say why.

## Stale index

The daemon usually re-indexes live, but re-run when a symbol you just added or
renamed is missing:

```bash
cd "/Users/meomeo/Documents/edit an3tocom apps&web"
codegraph sync          # prints "Already up to date" when current
```

Indexing is otherwise left to the owner; do not run `codegraph init` unprompted.
