# OpenScout Web

OpenScout Web is the product interface for evidence-backed GitHub repository discovery. It is a
React and Vite application with a dense repository-intelligence visual system.

## Product surfaces

- Discovery console with learning and contribution modes
- Constraint-aware recommendation results
- Repository evidence dossier
- Refreshed, unassigned contribution-Issue recommendations
- Three-way project comparison
- Device-local saves and recommendation feedback
- Deterministic evaluation results with visible failure cases

The search console calls the FastAPI service through Vite's `/api` development proxy. If the API
is unavailable, the interface preserves the submitted query and shows a clear recovery state; it
does not substitute demonstration repositories for live results.

## Development

```powershell
pnpm install
pnpm run dev
```

The local app runs at <http://127.0.0.1:5173> and expects the API at
<http://127.0.0.1:8000>.

## Production build

```powershell
pnpm run build
```
