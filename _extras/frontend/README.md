# ML Agent Studio — Frontend

Single consolidated React 19 + Vite + Tailwind CSS chat interface for the ML Agent pipeline.

## Development & Production Workflows

### 1. UI Development (`npm run dev`)
- Use `npm run dev` for fast, hot-reloading frontend development.
- The Vite dev server proxies `/ws`, `/upload`, and `/api` directly to the running backend at `http://127.0.0.1:8000`.
- Start the backend in one terminal (`python main.py` or `python server.py`) and run `npm run dev` in `frontend/`.

### 2. Production Serving (`npm run build`)
- Run `npm run build` to compile the optimized production bundle into `frontend/dist`.
- `server.py` and `python main.py` serve the compiled output directly from `frontend/dist` on `http://127.0.0.1:8000/`.
- In normal deployment, `server.py` serves the SPA bundle and handles WebSocket / REST endpoints from a single unified server.

## Features
- **Real WebSocket Streaming**: Real-time event communication over `/ws/session/{session_id}`.
- **Transparent Thinking**: Expandable reasoning traces surfaced at every stage (`data_explorer`, `planner`, `coder`, `execute`, `selector`).
- **Pipeline Stage Tracker**: Visual progress across all agent phases.
- **Interactive EDA & Plotting**: Automatic visualization of target correlations, class distributions, and execution plots.
- **Artifact Downloads**: Direct binary downloads for serialized model boosters, scripts, and exports.
