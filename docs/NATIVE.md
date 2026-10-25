# Native development

The supported complete demo is `python scripts/demo.py demo` with Docker Compose.
For development without Docker, install Python 3.12+, Node.js and PostgreSQL, and
create a dedicated database and role that owns it. PostgreSQL must be reachable
before starting the application. Never point tests at the demo database.

From the repository root on Windows PowerShell:

```powershell
python -m venv backend/.venv
& backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.lock
& backend/.venv/Scripts/python.exe -m pip install --no-deps -e backend
Push-Location frontend
npm ci
Pop-Location
python scripts/demo.py init
# Set DATABASE_URL in this shell to your role's PostgreSQL URL:
# postgresql+asyncpg://ROLE:PASSWORD@127.0.0.1:5432/DATABASE
& backend/.venv/Scripts/python.exe scripts/native.py --frontend
```

Keep the process running; Ctrl+C stops its children. The launcher applies
migrations, bootstraps the demo, checks ports before launch and writes ignored
logs under `.local/native/`. It binds API8000, receiver8081, frontend8080 and
worker metric ports9001-9003 to the local development topology. Vite binds
loopback. The worker metric servers should remain on a trusted local machine.
Administrator credentials are generated in ignored `.env`. Existing credentials
and database history are preserved on subsequent starts.

`--api-port` changes the API port and frontend proxy together. Monitoring is not
started by this launcher; use Compose for the provisioned monitoring stack.
Native monitoring verification performed during this build is recorded in
[MONITORING](MONITORING.md), rather than presented as an automatic installer.

In another terminal, with the same native database/application credentials:

```powershell
$env:DEMO_SINK_URL='http://127.0.0.1:8081'
& backend/.venv/Scripts/python.exe scripts/smoke.py --base-url http://127.0.0.1:8000
& backend/.venv/Scripts/python.exe scripts/failover.py --base http://127.0.0.1:8000
```

For backend tests, set `DATABASE_URL` to a separate database whose name ends
in `_test` or `_tests`. Fixtures drop and recreate its tables; a guard rejects
other database names. Run `python -m pytest` from `backend` using the virtualenv.
Frontend commands are `npm test`, `npm run lint`, `npm run typecheck`, and
`npm run build` from `frontend`. Browser tests need the live API/frontend and
administrator credentials; use `npm run test:e2e` with their environment configured.
