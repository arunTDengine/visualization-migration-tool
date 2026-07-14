# External LLM QA agent (harness)

After migrate, optionally score the published dashboard against the customer folder.

```bash
./harness/run-agent-workflow.sh full /path/to/customer-folder

# Or QA an existing report
./run.sh qa reports/latest.json --folder /path/to/customer-folder -o reports/latest-qa.json
```

Structural-only (no API key):

```bash
./run.sh qa reports/latest.json --folder /path/to/customer-folder --structural-only
```

Env: `QA_LLM_API_KEY`, `QA_LLM_PROVIDER=openai|anthropic`, `QA_LLM_MODEL`.

Does not change migrate — review only. Exit `0` pass, `2` fail, `3` needs_review.
