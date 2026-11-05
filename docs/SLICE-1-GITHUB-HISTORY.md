# Slice 1 — GitHub history

Start Extrude on loopback with `python -m uvicorn extrude.api.server:app --host 127.0.0.1 --port 8000`. Open **GitHub history** from Project Atlas, paste a GitHub repository URL, and import it. Git must be installed on the server machine.

- Select a commit to see added, removed, modified, or renamed files. Select a changed text file to read both versions side by side. A merge is compared with its first parent.
- Switch to **All files** to see the exact tree at the selected commit. KiCad PCB and schematic files have separate labels based on their extensions.
- Click **Sync from GitHub** after a push. **Compare with previous sync** shows the net change across all commits since the preceding distinct sync. The **History from** selector can reopen earlier imported tips.
- The app saves a bare Git repository under `EXTRUDE_DATA_DIR/github` (default `data/github`). The Git objects include the default branch's commit ancestry and file contents. Earlier imported tips stay available after a force push. A failed fetch leaves the last successful tip available.

Public repositories need only their URL. For a private repository, set `EXTRUDE_GITHUB_TOKEN` in the server environment or the local `.env` and restart the app. Use a token limited to the intended repository with read access to its contents. The server sends the token to GitHub over HTTPS and stores the fetched history on disk. Run this pilot on loopback, especially with private repositories. See [GitHub's HTTPS authentication guide](https://docs.github.com/en/get-started/git-basics/about-remote-repositories#cloning-with-https-urls).

## Scope

This is the local import stage. It fetches the default branch and its reachable history when asked. File previews are limited to 128 KB of UTF-8 text. Git keeps the underlying objects even when a file is too large to preview. Git LFS payloads and submodule contents require separate retrieval. The GitHub history view is separate from local folder scans.

The next parser can use the saved repository ID and exact base and head SHAs to retrieve a PCB or schematic at each revision. Automatic push delivery and shared access require the hosted GitHub App stage.
