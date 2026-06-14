# High-reasoning provider discovery — 20260613

## Scope

Discovery only. No implementation changes were made to the repo scripts.

Goal: identify the non-secret provider path Hermes uses for GPT-5.5 and recommend a safe Run 5 integration approach for the Terefo Heal Reboa repo.

Secrets policy used during inspection:

- Did not print API keys, tokens, OAuth material, cookies, credential values, or full secret-bearing config values.
- Reported only provider names, model names, config paths, key/env-var presence, and command shapes.

## Repo status at discovery start

`git status --short` showed only preserved untracked Run 1/2/3/4 files before this discovery report was written. No tracked files were dirty.

## Provider path found

Hermes CLI path:

```text
/home/ubuntu/.hermes/hermes-agent/venv/bin/hermes
```

Hermes version:

```text
Hermes Agent v0.16.0 (2026.6.5) · upstream 4474873d
```

Hermes config path:

```text
/root/.hermes/config.yaml
```

Hermes env path:

```text
/root/.hermes/.env
```

Relevant non-secret config values from `/root/.hermes/config.yaml`:

```yaml
model.provider: copilot
model.default: gpt-5.5
model.base_url: https://api.githubcopilot.com
delegation.provider: ""
delegation.model: ""
```

Provider classification:

- Provider name: `copilot`
- Model name: `gpt-5.5`
- Base URL: `https://api.githubcopilot.com`
- Provider type: GitHub Copilot / GitHub Models through Hermes' Copilot provider profile
- Not OpenAI API key
- Not OpenRouter
- Not direct OpenAI/Codex OAuth as currently configured
- Auth material source: Hermes credential/env system for Copilot; secret values not printed

Non-secret auth/config evidence:

- `/root/.hermes/.env` exists and contains key names including `COPILOT_GITHUB_TOKEN` and `GROQ_API_KEY`; values were not printed.
- `/root/.hermes/auth.json` exists and has a `credential_pool` entry for `copilot`; values were not printed.
- Current repo subprocess environment did not have `COPILOT_GITHUB_TOKEN` exported, which explains why repo scripts checking only process env did not detect it.

## Hermes provider implementation files

Provider profile:

```text
/home/ubuntu/.hermes/hermes-agent/plugins/model-providers/copilot/__init__.py
```

Important non-secret details:

- Class: `CopilotProfile`
- Registered provider name: `copilot`
- Aliases: `github-copilot`, `github-models`, `github-model`, `github`
- Env vars recognized by provider profile: `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`
- Base URL: `https://api.githubcopilot.com`
- Auth type: `copilot`
- For GPT-5+/Codex-family Copilot models, Hermes routes through a Responses/Codex adapter rather than plain `/chat/completions`.

Copilot auth helper:

```text
/home/ubuntu/.hermes/hermes-agent/hermes_cli/copilot_auth.py
```

Relevant functions/classes:

- `resolve_copilot_token()`
- `validate_copilot_token()`
- `copilot_device_code_login()`
- `copilot_request_headers()`

Credential search order documented in the helper:

1. `COPILOT_GITHUB_TOKEN`
2. `GH_TOKEN`
3. `GITHUB_TOKEN`
4. `gh auth token` fallback

Supported token classes are Copilot/GitHub OAuth/fine-grained/GitHub App style tokens; classic `ghp_*` PATs are explicitly not supported for Copilot API.

Auxiliary/provider wrapper:

```text
/home/ubuntu/.hermes/hermes-agent/agent/auxiliary_client.py
```

Relevant callables:

- `resolve_provider_client(provider, model, ...)`
- `call_llm(provider=..., model=..., messages=..., timeout=..., extra_body=...)`
- `async_call_llm(...)`
- `CodexAuxiliaryClient`
- `_CodexCompletionsAdapter`

For provider `copilot` and model `gpt-5.5`, `resolve_provider_client()` wraps the OpenAI SDK client in `CodexAuxiliaryClient` when Hermes determines the model requires the Responses API.

## Safe CLI command available to repo scripts

Yes. The safest no-import bridge is a one-shot Hermes CLI subprocess.

Command shape:

```bash
timeout 180 hermes chat \
  -Q \
  --provider copilot \
  -m gpt-5.5 \
  --source tool \
  -t safe \
  -q '<prompt requiring JSON only>'
```

Observed stdout format:

- `stdout`: final assistant response only in quiet mode (`-Q`)
- `stderr`: session metadata, e.g. `session_id: ...`

JSON output forcing:

- Can be prompt-enforced and then locally validated with `json.loads`.
- The CLI command itself does not expose a documented `--response-format json_schema` flag.
- Therefore Run 5 should treat JSON as **required but not trusted**: parse, validate schema, reject malformed output, and fail closed.

Timeout behavior:

- The CLI does not need repo code to implement internal timeout handling if called through an outer `timeout <seconds>` wrapper.
- Recommended repo setting: `TEREFO_LLM_TIMEOUT_SECONDS=180`.
- On external timeout, GNU `timeout` exits `124`.
- Hermes CLI success exits `0`.
- Hermes/provider/auth/model failures should be treated as nonzero and fail closed.

Recommended subprocess handling:

- Capture stdout/stderr separately.
- Parse only stdout as JSON.
- Redact stderr before writing reports.
- Do not pass secrets on command line.
- Set `--source tool` so sessions are tagged as tool/integration use.
- Use `-t safe` or omit toolsets if no tools are needed. For strict LLM-only canary/extraction, `-t safe` is the least-risk default.

## Safe Python module path available to repo scripts

Yes, but it couples repo code to Hermes internals and source checkout paths.

Import path tested successfully:

```bash
PYTHONPATH=/home/ubuntu/.hermes/hermes-agent python3 - <<'PY'
from agent.auxiliary_client import call_llm
PY
```

Import example:

```python
from agent.auxiliary_client import call_llm

resp = call_llm(
    provider="copilot",
    model="gpt-5.5",
    messages=[
        {"role": "system", "content": "Return valid JSON only. No markdown."},
        {"role": "user", "content": prompt},
    ],
    timeout=120,
    extra_body={"reasoning": {"effort": "low"}},
)
text = resp.choices[0].message.content
```

Structured JSON support:

- `call_llm()` supports chat messages, tools, timeout, max tokens, temperature, and `extra_body`.
- It does not expose a dedicated `response_format` parameter in its public signature.
- For Copilot GPT-5.5, Hermes routes through its Responses adapter; strict JSON should still be validated by repo code after receipt.
- Stronger schema enforcement may be possible through tool/function schemas, but this discovery did not implement or verify that path.

Risk:

- Direct import depends on `/home/ubuntu/.hermes/hermes-agent` being present and API-compatible.
- It is less stable than calling the installed `hermes` CLI.

## Canary results

### Hermes CLI canary

Command used:

```bash
timeout 180 hermes chat -Q --provider copilot -m gpt-5.5 --source tool -t safe -q 'Return JSON only: {"ok": true, "model": "<model-name>", "reasoning": "available"}. Use model "gpt-5.5". No markdown, no prose.'
```

Exit code:

```text
0
```

Stdout:

```json
{"ok":true,"model":"gpt-5.5","reasoning":"available"}
```

Stderr:

```text
session_id: 20260613_180733_cb219b
```

Parsed JSON:

```json
{
  "ok": true,
  "model": "gpt-5.5",
  "reasoning": "available"
}
```

Conclusion: Hermes CLI can invoke GPT-5.5 through provider `copilot`, and a strict JSON canary can be parsed successfully.

### Hermes Python auxiliary canary

Command shape used:

```bash
PYTHONPATH=/home/ubuntu/.hermes/hermes-agent timeout 180 python3 - <<'PY'
from agent.auxiliary_client import call_llm
# call_llm(provider='copilot', model='gpt-5.5', messages=[...], timeout=120, extra_body={'reasoning': {'effort': 'low'}})
PY
```

Exit code:

```text
0
```

Parsed JSON:

```json
{
  "ok": true,
  "model": "gpt-5.5",
  "reasoning": "available"
}
```

Conclusion: direct Python integration through Hermes internals also works when `PYTHONPATH` includes the Hermes checkout.

## Can repo scripts call GPT-5.5 directly?

Yes, through either:

1. Hermes CLI subprocess — recommended least-risk bridge.
2. Hermes Python internal module import — works, but less stable and more tightly coupled.

Repo scripts should **not** attempt to call `https://api.githubcopilot.com` directly in Run 5 unless they also reimplement Hermes' Copilot auth headers, token resolution, model routing, and Responses adapter behavior. That would be higher risk.

## Recommended Run 5 integration approach

Recommended bridge: **local wrapper script around Hermes CLI**, called by `scripts/llm_source_cards.py` and `scripts/llm_extract_semantic_objects.py`.

Why:

- Uses the same provider path Hermes already uses successfully.
- Avoids exposing or duplicating secret handling in the repo.
- Avoids depending directly on Hermes internal Python APIs.
- Keeps repo scripts hermetic enough to test by swapping the command.
- Allows strict local schema validation in repo scripts.

Recommended Run 5 flow:

1. Add a small repo wrapper, for example:

```text
scripts/hermes_high_reasoning_json.py
```

or use direct subprocess construction inside the two existing scripts if a wrapper is considered too much surface area.

2. Wrapper behavior:

- Accept JSON input on stdin:

```json
{
  "system": "Return JSON only...",
  "prompt": "...",
  "schema_name": "source_card|semantic_object|canary",
  "timeout_seconds": 180
}
```

- Invoke:

```bash
timeout "$TEREFO_LLM_TIMEOUT_SECONDS" hermes chat -Q --provider "$TEREFO_LLM_PROVIDER" -m "$TEREFO_LLM_REASONING_MODEL" --source tool -t safe -q "$PROMPT"
```

- Parse stdout as JSON.
- Return normalized JSON on stdout:

```json
{
  "ok": true,
  "provider": "copilot",
  "model": "gpt-5.5",
  "text": {...},
  "raw_stdout_hash": "...",
  "stderr_redacted": "...",
  "exit_code": 0
}
```

- On failure, return nonzero and a redacted JSON error object.

3. `scripts/llm_source_cards.py` Run 5 change:

- Replace the current high-reasoning detection-only behavior with an optional call to the wrapper when:
  - `--no-llm` is false, and
  - `--require-high-reasoning` or equivalent is requested, and
  - `TEREFO_HIGH_REASONING_MODEL_AVAILABLE=true` or a canary succeeds.
- Keep default report-only/no-write behavior.
- Validate LLM JSON against existing source-card schema.
- Reject malformed JSON and do not persist invalid output.

4. `scripts/llm_extract_semantic_objects.py` Run 5 change:

- Use the same wrapper for:
  - `--llm-canary-only --require-high-reasoning`
  - real semantic extraction when high-reasoning is available
- Require strict schema validation before writing reports or optional semantic notes.
- Continue reading only from `source_notes.note_type='source_card_draft'`.
- Continue default no-DB-write behavior.

## Suggested non-secret repo configuration for Run 5

Add `.env.example` entries only, not real secrets:

```bash
# High-reasoning provider bridge for Terefo Heal Reboa pipeline
TEREFO_LLM_PROVIDER=copilot
TEREFO_LLM_REASONING_MODEL=gpt-5.5
TEREFO_LLM_COMMAND=hermes
TEREFO_LLM_TIMEOUT_SECONDS=180
TEREFO_HIGH_REASONING_MODEL_AVAILABLE=false

# Optional: force use of Hermes CLI bridge instead of direct API/provider calls
TEREFO_LLM_BRIDGE=hermes_cli

# Optional: toolsets passed to Hermes for isolated LLM-only subprocesses
TEREFO_LLM_TOOLSETS=safe

# Optional: source tag for Hermes sessions created by repo scripts
TEREFO_LLM_SOURCE_TAG=tool
```

Do not add API keys to the repo `.env.example` beyond placeholder names. The actual Copilot credential should remain in Hermes-managed config/env/auth storage.

Recommended script/config keys:

- provider selection: `TEREFO_LLM_PROVIDER`
- model selection: `TEREFO_LLM_REASONING_MODEL`
- command selection: `TEREFO_LLM_COMMAND`
- timeout: `TEREFO_LLM_TIMEOUT_SECONDS`
- bridge mode: `TEREFO_LLM_BRIDGE`
- toolsets: `TEREFO_LLM_TOOLSETS`
- source tag: `TEREFO_LLM_SOURCE_TAG`
- high-reasoning gate: `TEREFO_HIGH_REASONING_MODEL_AVAILABLE`

Run 5 should not require `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENROUTER_API_KEY` for this environment.

## Risks / limitations

- `hermes chat -Q` can be prompt-enforced to return JSON, but the CLI does not expose a documented strict JSON schema flag. Repo scripts must validate and reject bad output.
- Direct Python import from `/home/ubuntu/.hermes/hermes-agent` works but is internal and may change with Hermes updates.
- The CLI subprocess creates Hermes sessions; use `--source tool` and perhaps a distinctive prompt prefix to separate these from user chat sessions.
- The current Hermes installation is behind upstream; future updates could change internal APIs or provider routing.
- Long-running LLM calls need an outer timeout; recommended `timeout 180` with GNU timeout semantics.
- If the gateway/session environment differs from local shell environment, direct repo subprocesses should call the installed `hermes` command rather than expecting provider env vars in the repo process.
- A successful canary proves availability, not semantic quality. Run 5 should still keep report-only defaults and validate all objects.

## Files likely needing changes in Run 5

Likely:

- `scripts/llm_source_cards.py`
- `scripts/llm_extract_semantic_objects.py`
- `tests/test_llm_source_cards.py`
- `tests/test_llm_extract_semantic_objects.py`
- `.env.example` if present, or equivalent docs/config example
- `reports/architecture/run5-...md` evidence map

Optional:

- `scripts/hermes_high_reasoning_json.py` as a shared wrapper
- tests for the wrapper with a fake `TEREFO_LLM_COMMAND`

Not recommended for Run 5:

- changing `data/schema.sql`
- changing `scripts/daily_book_worker.py`
- changing commit allowlist logic
- writing chapter prose
- direct Copilot API implementation inside repo scripts

## Bottom-line recommendation

Run 5 should integrate high reasoning through a **Hermes CLI JSON bridge** using:

```bash
timeout 180 hermes chat -Q --provider copilot -m gpt-5.5 --source tool -t safe -q '<strict JSON prompt>'
```

Then both Run 5 script paths should:

1. parse stdout as JSON,
2. validate against their local schema,
3. set `llm_used=true` only after a successful canary and successful schema validation,
4. keep DB writes disabled by default,
5. fail closed on timeout, nonzero exit, invalid JSON, schema mismatch, or weak/local fallback.
