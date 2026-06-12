# SPPS EdTech

An independent, parent-run website about the role of technology in Saint Paul
Public Schools: the history of how screens arrived in every classroom, what
current district policy and Minnesota law actually say, how SPPS compares to
districts with stronger limits, and how families and teachers can get involved.

**Live site:** https://kgerbner.github.io/SPPSEdTech/

Built with [Astro](https://astro.build), deployed to GitHub Pages. Not
affiliated with Saint Paul Public Schools.

## Editing the content (no coding required)

All of the site's facts live in four YAML files in `src/data/`:

| File | Drives |
| --- | --- |
| `timeline.yaml` | The interactive timeline on the History page |
| `districts.yaml` | The cards on the How SPPS Compares page |
| `resources.yaml` | Books / research / articles / orgs on Learn More |
| `involvement.yaml` | Action items on Get Involved |

Each file starts with a `HOW TO EDIT` comment describing its fields. Two rules
are enforced at build time: every timeline and district entry **must cite at
least one source URL**, and category names must come from the fixed list. A bad
edit fails the build with a readable error instead of silently breaking a page.

Edit a file on GitHub (pencil icon), commit, and the site rebuilds and deploys
automatically.

## How the automatic policy monitoring works

The site promises to stay current when SPPS or the state changes the rules.
That's the **policy watch** ( `.github/workflows/policy-watch.yml` ):

1. Every Monday morning, GitHub Actions runs `scripts/policy_watch.py`.
2. The script fetches each page listed in `policy-watch.json` (SPPS board
   policy pages, the Rights & Responsibilities handbook, Minn. Stat.
   § 121A.73), strips it to plain text, and compares it against the snapshots
   committed in `policy-snapshots/`.
3. **If anything changed**, it opens a pull request containing the diff. That
   PR is your to-do item: update `src/data/timeline.yaml` and/or
   `src/pages/policy.astro` (including its `lastVerified` date) on the PR
   branch if the change warrants it, then merge. Merging records the new
   snapshot as the baseline.
4. **If a monitored page is unreachable three weeks running** (moved, deleted,
   or blocking GitHub's servers), it opens an issue instead so the URL can be
   fixed in `policy-watch.json`.

To add a monitored page, add an entry to `policy-watch.json` (`type` is
`html` or `pdf`); the next run creates its baseline snapshot automatically.
You can trigger a run any time from the Actions tab → Policy watch → Run
workflow.

## Local development

```sh
npm install
npm run dev        # local preview at http://localhost:4321/SPPSEdTech/
npm run build      # production build (also validates the YAML data files)
npm run preview    # serve the production build
```

## Deployment

Pushes to `main` deploy automatically via `.github/workflows/deploy.yml`.
One-time setup: repository **Settings → Pages → Source → "GitHub Actions"**.

The site is configured for `https://kgerbner.github.io/SPPSEdTech/`
(`base: '/SPPSEdTech'` in `astro.config.mjs`). If you later attach a custom
domain, change `site`/`base` there — internal links all go through the
`href()` helper in `src/utils.ts`, so nothing else needs to change.
