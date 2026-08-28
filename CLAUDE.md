# Token efficiency

- Always respond to the user in Brazilian Portuguese. Keep code, commands, file paths, identifiers, and technical names in their original language.
- Use low effort by default. Never raise the effort level unless the user explicitly requests it.
- For routine UI or CSS changes, make the smallest targeted edit. Do not invoke skills, subagents, browsers, screenshots, or visual automation unless the user explicitly requests them.
- Search only inside `LCK_Predictor_V28_AUTO_DRAFT/`. Use targeted Grep and bounded Read; never scan the workspace root or read large/minified files wholesale.
- For home and top-navigation UI, inspect `static/js/05-page-home.js`, `static/css/15-topnav-modern.css`, and then `static/css/01-base-shell.css` before searching elsewhere.
- Do not repeat failed approaches or checks. After five tool calls without a clear solution, stop and ask the user instead of continuing autonomously.
- Do not reread a file after a successful edit and do not verify the local server unless the user asks.
- Batch related edits into as few model calls as practical.
- If the conversation context becomes large, recommend starting a fresh session with a concise handoff instead of continuing indefinitely.

The application is in `LCK_Predictor_V28_AUTO_DRAFT/` and runs at `http://127.0.0.1:8828/`.
