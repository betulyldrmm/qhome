# QHome React frontend

The React + TypeScript + Vite application currently contains the Dashboard only.
It reads the existing QHome REST API and posts device commands to the same backend.

```powershell
npm install
npm run dev
```

Start the Python backend on port 7000 before opening the Vite development URL. The Vite
development proxy forwards `/api/*` requests to `http://127.0.0.1:7000`.

`npm run typecheck` checks TypeScript. `npm run build` creates a static production bundle
in `dist/`. The existing Python server still serves `assets/`; switching production traffic
to this new bundle is intentionally a separate integration step so the legacy frontend and
backend remain untouched during this migration.
