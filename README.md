# Quantum Papers — local prototype

One original Markdown paper, registered in folders across multiple vaults.
Uses Python 3.10+ and its standard library; no package installation required.

## Try the isolated demo

```sh
python quantum.py --demo --state /tmp/quantum-papers-demo
```

Open the local server on port 8765 in your browser. Select Research → Papers,
open “One paper.md”, then select Writing → Ideas and open the same paper.
Edit and save from either location. “Show here too” adds a folder membership;
“Move original” physically moves the file, including between vaults.
Writing → Papers contains a linked note: its paper link still resolves after a move.

To connect existing vaults, pass `--vault /absolute/path/to/vault` for each vault.
Use “Register a Markdown file” with a vault-relative path. Registering and adding
memberships do not duplicate or modify the file. Saving and moving modify real
files; use backed-up test vaults during this prototype stage.

```sh
python -m unittest discover -s tests -v
```

## Current boundaries

- Local, single-user browser workspace, bound to loopback. No network sharing yet.
- Folder memberships live in the SQLite registry under `--state`; back it up along
  with your vaults. Keep the same server address for copied browser links.
- Links use permanent registry IDs. Moves made through this app preserve them.
  External moves/renames are not reconciled yet.
- Markdown source editing and internal paper-link navigation; no rich rendering yet.
- This is not yet an installable Obsidian plugin. Native Obsidian explorer entries,
  cross-device sync, automatic file discovery, external link handlers, authentication,
  concurrent editing conflict handling, and crash-safe file moves are future work.
- Existing ordinary Obsidian links are not rewritten when a file moves.

Use the existing checkout for development; cloud tasks are already isolated.
