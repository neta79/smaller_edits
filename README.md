# smaller_edits

`smaller_edits` is a small experiment in making file edits less annoying for LLMs.

Instead of asking a model to recite half a file back at the harness, it reads lines like this:

```text
123,ujzi|The actual line content, which may be very long and may even repeat elsewhere in the file
```

Then it edits by pointing at the tiny handle (`123,ujzi`) rather than restating the whole line.

In short: less diff karaoke, more pointing.

## The Pitch

The toolset is a Proof of Concept that has two core operations:

- `read(path, offset, limit)`
- `edit(...)`

`read()` returns line-numbered, line-hashed output.
`edit()` uses those anchors to replace, insert, or delete contiguous ranges.

The specs are here:

- `spec/smaller-edits-spec.md`

The current Python reference implementation lives here:

- `python/src/smaller_edits/`

The Agno-based test harness lives here, away from the core implementation:

- `python/test/harness.py`

## Pros

- Tiny edit references instead of giant verbatim diff chunks
- Repeated identical lines are still distinguishable
- The model gets refreshed context after edits
- The core implementation is testable without any specific agent framework
- There is now a reusable vector set under `test/`

## Cons

- This is still a protocol, not magic
- Models must pay attention to fresh anchors after each edit
- Very weak models still get confused by tool manifests surprisingly easily
- Harness wording matters a lot
- If you make the manifest too clever, tiny models will absolutely use the cleverness against you

## Repo Map

- `spec/smaller-edits-spec.md`: the formal specification
- `python/src/smaller_edits/`: Python reference implementation
- `python/test/`: harness, unit tests, and functional tests
- `test/fixtures/`: reusable text fixtures
- `test/vectors/`: expected read/edit/harness outcomes

## Quick Start

Install the Python package from the `python/` directory in editable mode if needed:

```bash
python -m pip install -e python
```

Run the Python unit tests:

```bash
cd python
python3 -m unittest discover -s test
```

Run one live harness vector against a model/endpoint:

```bash
python/test/run_harness_test.sh harness:full-read-line-anchor
```

The shell wrapper is intentionally easygoing:

- it uses `python/venv/` if present
- it auto-picks a root `.env` if found
- it can target local Ollama-compatible endpoints
- it prints the LLM/tool dialogue in plain text while running

## Weak-LLM Status Report

This project was tested not only with stronger hosted models, but also with hilariously small local ones.

What has worked in live harness runs, one vector at a time:

- `gemma4:e2b` completed basic insert/replace flows
- `qwen3:0.6b` completed selected insert, replace, and delete vectors after the harness manifest was simplified
- brace-wrapped anchors and full-read-line anchor reuse were exercised in the harness vectors

What this does **not** mean:

- tiny models are now wise
- the problem is solved forever
- every manifest wording is equally good

What it **does** mean:

- the protocol is viable enough to survive contact with extremely weak models
- manifest design is a first-class part of the problem
- a lean, concrete tool description works much better than a huge "helpful" one

## Current Mood

Promising, a bit scrappy, and still very much experimental.

Which is honestly the correct mood for a repo about teaching small models to edit files without eating the furniture.
