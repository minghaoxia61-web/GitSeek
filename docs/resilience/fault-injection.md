# External-service fault injection

GitSeek includes a deterministic proxy for exercising GitHub degradation paths without making
network requests. `FaultInjectingClient` wraps a normal test client and injects a timeout, API error,
or rate limit on selected call numbers. The same production services and API routes are then used
unchanged.

## Scenarios in the quality gate

| Scenario | Expected behavior |
| --- | --- |
| All live-search calls time out | Return local-index recommendations and mark GitHub unavailable |
| One candidate's comment lookup times out | Keep the Issue and mark response evidence unknown |
| Issue refresh is rate-limited | Return the saved Issue list with `data_status=stale` |
| Issue refresh has a transport failure | Return the saved Issue list with `data_status=stale` |

The stale response also carries a machine-readable degradation reason. The web dossier displays a
warning and tells the user to confirm the Issue on GitHub before starting work.

Run only the resilience suite:

```powershell
.\.venv\Scripts\python -m pytest tests/resilience -q
```

## Boundary

These scenarios prove deterministic application behavior, not GitHub availability. The in-memory
runtime counters and rate limiter remain process-local, and a multi-instance deployment would need
shared infrastructure before claiming distributed resilience.
