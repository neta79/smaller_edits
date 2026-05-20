# smaller_edits

`smaller_edits` is a small experiment in making file edits less annoying for LLMs.

In short: no diff karaoke, more finger pointing.

Instead of asking a model to recite half a file back at the harness, it reads lines like this:

```text
123,ujzi|The actual line content, which may be very long and may even repeat elsewhere in the file
```

Then it edits by pointing at the tiny handle (`123,ujzi`) rather than restating the whole line.

Any problems? Well, it works. And it works better than naked hash references. (They fail in the identical-lines case)
But it's still **VERY brittle** dealing with sequences of repeated lines. 

It gives no guarantees of success, actually: any previous additive or subtractive edit may have shifted the line numbers, and you can bet the LLM is going at some point to call edit() with the wrong anchors. 

Here is a candidate spec for a runtime model that does two things:

1. solves that for good (allegedly);
2. and basically lies to the LLM, for a good cause: To reduce context churn to a minimum, eliminate as many invalidations and rereads as possible.

## Credits

The original idea comes from [@antirez](https://antirez.com), which 
[briefly](https://antirez.com/news/166) mentioned the 
[concept](https://www.youtube.com/watch?v=IoE3Hi2zpwk#t=22m10s).


## The Pitch

The toolset is a Proof of Concept that has two core operations:

- `read(path, offset, limit)`
- `edit(...)`

`read()` returns line-numbered, line-hashed output (with some chained hashing in the mix).
`edit()` uses those anchors to replace, insert, or delete contiguous ranges.

The two tools share a state and must cooperate behind the scenes to keep the anchors valid and the model's view of the file consistent. 

It's not that complex, not it is orthodox, but it helps smaller LLMs immensely.

Full specs are here:

- `spec/smaller-edits-spec.md`

The current Python reference implementation lives here:

- `python/src/smaller_edits/`

The Agno-based test harness lives here, away from the core implementation:

- `python/test/harness.py`

## Pros

- Tiny edit references instead of giant verbatim diff chunks
- Repeated identical lines are still distinguishable, and dealth with correctly
- The model gets refreshed context after edits (optional, not a requirement)
- Edit manifest can be presented from top-tier multi-patch in a single call down to very barebones 2-parameter callable vof VERY small models.

## Cons

- This is still a protocol, not magic
- Smaller models stop corrupting stuff by accident, but they can still call the tool wrong and incur in forced rereads
- Very weak models still get confused by tool manifests surprisingly easily
- Harness wording matters a lot. There's some art to it.
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

## .env Setup

The harness will auto-load a root `.env` if it finds one.

For hosted OpenAI, a minimal `.env` looks like this:

```dotenv
OPENAI_API_KEY=sk-...
```

For a local OpenAI-compatible endpoint such as Ollama, you usually want the test wrapper variables instead:

```dotenv
LINEHASH_TEST_MODEL=qwen3:0.6b
LINEHASH_TEST_BASE_URL=http://127.0.0.1:11434/v1
LINEHASH_TEST_API_KEY=ollama
```

Same idea for any other local OpenAI-compatible server: set the model name, set the base URL, and give it whatever dummy API key that server expects.

## Weak-LLM Status Report

This project was tested not only with stronger hosted models, but also with hilariously small local ones.

What has worked in live harness runs, one vector at a time:

- `gemma4:e2b` completed basic insert/replace flows. It's strong. No problem there.
- `qwen3:0.6b` completed selected insert, replace, and delete vectors after the harness manifest was simplified

We pushed down to `granite4:350m`, which is is probably the benchmark for the tinyest tool-capable model that can 
still do something nontrivial. What this taught us:

- it is very easy to overwhelm tiny models with a "helpful" tool manifest
- abstract placeholders like `{lineno},{chainHash}` are dangerous; the model may literally type `lineno` back at you
- even when a model understands anchors in principle, it may still:
  - omit required fields like `path` or `kind`
  - confuse `kind` with `type`
  - copy example paths instead of the current file path
  - stop after `read()` and never perform the `edit()`
  - misread the returned post-edit window and claim success when it actually inserted instead of replaced

Plausible mitigations we found:

- prefer concrete examples over abstract schema explanations
- keep the manifest short, repetitive, and literal
- say what **not** to do in plain language, for example: do not use `beta` as an anchor
- include one exact example per operation shape you care about
- tell the model explicitly that example anchors are patterns only, not reusable values
- reduce optionality where possible; tiny models do worse when a tool supports too many calling conventions
- if tiny models are a serious target, splitting one polymorphic `edit(...)` tool into several narrower tools is probably worth testing
- completely opaque handles could probably be used to enforce reference correctness, but at this point it means we are just barking at the wrong LLM.

What this does **not** mean:

- tiny models are now wise
- the problem is solved forever
- every manifest wording is equally good

What it **does** mean:

- the protocol is viable enough to survive contact with extremely weak models
- manifest design is a first-class part of the problem
- a lean, concrete tool description works much better than a huge "helpful" one

## Takeaways

If there's one thing to take away, it's *"LLKPAIII"*, obviously:

- `[L]`et the LLM point at lines using tiny anchors like `123,abcd`.
- `[L]`et the harness do the annoying bookkeeping.
- `[K]`eep the shared state sparse but indexed.
- `[P]`refer block replacements over fussy one-line surgery.
- `[A]`nd Always hand back fresh context after each edit. 
- `[I]`f the file drifted, fail cleanly.
- `[I]`f the span was never read, fail honestly.
- `[I]`f everything lines up, apply the edit without making the model recite half the bible like it is being punished for something.

## Organic

This project is *mostly* organic and burned a reduced amount of tokens by using a human.

*More ATPs, less APIs.*

*Save some tokens.*

*Go green.*

