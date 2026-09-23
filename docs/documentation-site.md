# Documentation site

The public [documentation site](https://turbomam.github.io/feature-table-corpus/)
is built from the repository's existing Markdown. **The model and conversion
profiles remain drafts.** NMDC analyses describe NMDC records, not universal
requirements for every producer.

## Build and preview

```sh
just docs-build
just docs-serve 8765
```

Preview at <http://127.0.0.1:8765/feature-table-corpus/>. The server binds to
loopback. Use another port if needed. Add new public documentation files to Git
before building: the staging step includes only tracked/staged files, using their
current working-tree contents. Re-run after editing; preview serves the staged
copy. `just docs-check` checks an already built site's local links and fragments.

[MkDocs](https://www.mkdocs.org/) with
[Material](https://squidfunk.github.io/mkdocs-material/) supplies navigation,
search, tables, code blocks, and Mermaid rendering without relocating prose.
[requirements-docs.txt](../requirements-docs.txt) pins the direct dependencies.
Mermaid's browser renderer is loaded by the theme; it requires network access.
The Markdown diagram source remains available in the repository.

## One maintained source

[mkdocs.yml](https://github.com/turbomam/feature-table-corpus/blob/main/mkdocs.yml)
defines reading paths for evidence, draft contracts, executable examples, and
explicitly NMDC-specific reports. `scripts/prepare_docs.py` stages allowed tracked
files from `docs/`, `model/`, `analyses/`, `corpus/`, `scripts/`, and `tests/`, plus
named root files, under gitignored `local/site-src/`. Source/data/code artifacts
remain downloadable. Directory indexes are generated navigation, not a second
maintained prose tree. The built site goes in `local/site/`.

Files under `local/`, untracked downloads, dotfiles, private research notes,
database binaries, and external symlinks are excluded. The build does not scan
Desktop notes or retrieve participant traces. Adding new public roots or file
types requires changing the explicit publication allowlist.

## Checks and deployment

Every PR runs a strict build and checks every built local HTML link, fragment,
and resource reference. External URL availability is outside this offline check.
PR builds produce a downloadable Actions preview artifact and have no deployment
permissions. Successful main-branch builds upload a Pages artifact; a separate
deployment job alone receives `pages: write` and `id-token: write`, using the
`github-pages` environment. Manual dispatch also deploys only from main.
Runs for the same PR or branch never overlap: main builds queue, and a newer PR
push cancels the older PR build. GitHub does not guarantee queue order, so the
deploy job skips any build whose commit is no longer the head of main.

The repository Pages setting must use **GitHub Actions**. The workflow becomes
active when this change reaches main; a PR preview does not establish that the
public URL has deployed. If deployment fails, inspect the documentation workflow
and Pages environment/settings before claiming publication succeeded.
