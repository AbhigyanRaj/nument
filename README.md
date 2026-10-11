# nument

Multi-plant order allocation with cost and carbon. nument decides which plant builds each
order and in which week, trading off landed cost, CO2e and delivery dates. Every number comes
from a deterministic solver; the LLM only reads the request and writes the words, and every
figure it writes is checked against the computed facts.

> Work in progress. The full README (architecture, quick start, API, rules and formulas,
> evaluation) lands with the final release.

## Development setup

```bash
uv venv --python 3.11
uv pip install -r requirements-dev.lock
git config core.hooksPath .githooks   # commit hygiene checks
cp .env.example .env                  # add an LLM key, or leave blank for mock mode
.venv/bin/python -m pytest -q
```
