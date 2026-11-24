# Contributing

Thanks for helping. Keep changes small and focused.

- Python 3.10+. Standard library only: no new dependencies, no network calls.
- Run the test suite with `python -m unittest discover -s tests -t .`. All tests must pass.
- Add a test for every behaviour change. Use temp folders and `MENTAT_CONFIG` to sandbox config;
  never touch the real home folder or `~/.claude`. Subprocess tests use
  `sys.executable -m mentat_wiki`.
- One pull request, one behaviour. Explain what changed and why.
- Match the existing style: short functions, small modules, plain names, no frameworks.
- Keep it cross-platform. No shell-specific commands, no hard-coded separators, no Windows launcher
  aliases in code or docs. The agent-facing command comes from `config.command()`.
- Use `pathlib`, explicit `encoding="utf-8"`, `util.write_atomic` for writes, `util.lock` around
  vault state changes, and `util.privacy_scan` / `Vault._guard` before writing user text.
- Never put personal data in code, tests, docs, or fixtures. Use fictional examples: `my-app`, a
  vault at `~/vault`, generic names, and `example.com` placeholders.
- Hooks and the status line must never fail loudly: catch errors and exit 0 (hooks print nothing).
- Docs are plain English, short sentences, no hype words, no emojis.

Open an issue before large changes so the work is not wasted.
