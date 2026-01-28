# Hugin

[![CI](https://github.com/gimlelabs/gimle-hugin/actions/workflows/ci.yml/badge.svg)](https://github.com/gimlelabs/gimle-hugin/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

<p align="center">
  <img src="https://raw.githubusercontent.com/gimlelabs/gimle-hugin/main/hugin.gif" alt="Hugin demo" width="900" />
</p>

A framework for building agents with a focus on longer running, creative, reasoning tasks.

## Quick Start

```bash
pip install gimle-hugin
hugin create
```

## Documentation

Full documentation at **[hugin.gimlelabs.com](https://hugin.gimlelabs.com)**

- [Getting Started](https://hugin.gimlelabs.com/getting-started/)
- [Core Concepts](https://hugin.gimlelabs.com/concepts/)
- [CLI](https://hugin.gimlelabs.com/cli/) - Learn the command line interfaces
- [Examples](https://hugin.gimlelabs.com/examples/)
- [API Reference](https://hugin.gimlelabs.com/api/)

## Development

```bash
git clone https://github.com/gimlelabs/gimle-hugin.git
cd gimle-hugin
uv sync --all-extras
uv run pytest
```

## Vibe Coding

I am a big fan of vibe coding and one of the intentions of Hugin was to make a framework simple and clean enough for coding agents to use it to build their own agents and agentic apps.

As a show case of this, all the apps in the `apps` folder are 100% vibed (which does show a bit in terms the code quality 😄) using either Claude Code or Cursor.

Generally, I think they did a pretty good job, so I have left them as vibed and so far I haven’t found any bugs in the agentic flows - but lots in the UI 😆.

Similarly all the tests and much of the CLI are mostly vibed - although this had to do more with time constraints than anything else.

## Why "Hugin"?

In old Norse, Hugin means thought and is the name of one of Odin's ravens. The other being Munin, meaning memory.
I think that is quite a fitting name for an agentic framework 😃
