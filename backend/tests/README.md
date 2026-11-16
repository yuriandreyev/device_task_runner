# Reliability test coverage (T07)

Run `uv run pytest` or `make verify` from the repository root. Database tests use
the configured PostgreSQL service and create an isolated Django test database.
The test database user needs permission to create databases. No SQLite substitute
is used for lock tests. Device/token fixtures create their own rows for each test;
worker threads open their own connections and close them on exit.

| Behavior | Coverage |
| --- | --- |
| Administrative create/read, validation and permissions | `integration/tasks/presentation/test_views.py`, `test_permissions.py` |
| Empty queue, claim/lease/reclaim, device isolation | `integration/tasks/presentation/test_claim.py` |
| Simultaneous claims, exactly one issued attempt | `test_claim.py::test_concurrent_claims_return_exactly_one_attempt` (barrier, distinct PostgreSQL backend sessions) |
| Skip locked rows and failed claim rollback | `integration/tasks/infrastructure/storage/test_task_repository.py` |
| Successful/failed result, identical/conflicting retry, expired lease, stale token | `integration/tasks/presentation/test_result.py` |
| Concurrent identical/conflicting results | `test_result.py::test_simultaneous_results_are_serialized` |
| Completion racing with reclaim, in both lock orders | `integration/tasks/infrastructure/storage/test_result_reliability.py` (events, ORM execution hook, no sleeps) |
| Result transaction failure and safe retry | `test_result_reliability.py::test_failed_result_transaction_rolls_back_all_fields_and_can_be_retried` |
| JSON key order and boolean/number distinction; failed-result conflicts | `integration/tasks/presentation/test_result.py` |
| Actual host data and controlled collection failure | `unit/agent/test_actions.py` |
| Mock HTTP claim/collect/result, identical-byte delivery retries, one execution | `unit/agent/test_runner.py` |
| Continuous polling recovery, conflict handling, timeouts, jitter, unsupported actions | `unit/agent/test_runner.py` |
| Backend accepts result but acknowledgment is lost | `integration/agent/test_backend.py` |
| Standalone `python -m agent --once`, empty queue and collection | `integration/agent/test_cli.py` |

Race tests use bounded waits and release held locks in `finally` blocks. The
completion/reclaim test forces both lock orders: completion first makes the claim
skip the locked row; reclaim first causes the old result token to be rejected.
Only ORM queries are used. Result rollback tests inject failure after the write
and assert every persisted field is restored before retrying the same submission.

T07 also verifies the full suite in a seeded shuffled order to look for fixture
or global-state dependencies. No test-randomization dependency is needed: pytest's
`pytest_collection_modifyitems` hook can shuffle the collected items with a local
`random.Random` instance. T08's manual demo and clean-start checks remain separate.

## Optional presence (T09)

`unit/tasks/application/use_cases/test_get_presence.py` covers device lookup and
all presence states. `integration/tasks/presentation/test_presence.py` covers
user/device authentication, marker-only writes, Redis exceptions and genuine
connection refusal with unchanged task lifecycle behavior. Integration fixtures
isolate application Redis access from the developer's configured URL.

Start Redis with `make redis-up`, then run
`TEST_REDIS_URL=redis://127.0.0.1:6379/15 make verify` for the real Redis tests in
`integration/tasks/infrastructure/test_presence.py`. They use unique keys and
remove only those keys. They check the production 90-second TTL and refresh,
then real expiry using a one-second test TTL. Without TEST_REDIS_URL these two
tests skip; other presence/failure tests still run.
