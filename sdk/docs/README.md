# Bittensor docs

Next.js + Fumadocs site for the subtensor SDK/CLI, built to be the agentic
lookup surface for doing anything on Bittensor.

The reference section (`content/docs/tx`, `content/docs/query`,
`content/docs/errors.mdx`) and the JSON catalogs (`public/catalog/`) are
**generated** from the SDK's own registries — never edit them by hand:

```bash
source ../python/.venv/bin/activate
python scripts/generate.py            # regenerate
python scripts/generate.py --check    # CI drift gate
```

Everything else under `content/docs/` is hand-written.

```bash
pnpm install
pnpm dev      # http://localhost:3000
pnpm build
```

Agent-facing endpoints: `/llms.txt`, `/llms-full.txt`, raw markdown for every
page under `/llms.mdx/docs/<slug>/content.md`, and the catalogs at
`/catalog/{intents,reads,errors}.json`.
