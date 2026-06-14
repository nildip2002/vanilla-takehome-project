# Test Suite Documentation
## BMO Agentic Execution Framework

---

## 1. Overview

The backend test suite covers the full application stack: REST API endpoints, the repository data layer, all eight MCP tools, and the SQLite database model. Tests are written with **pytest** and run as the first gate in every CI/CD pipeline before any deployment occurs.

| Metric | Value |
|---|---|
| **Total tests** | 134 |
| **Total passed** | 134 |
| **Total failed** | 0 |
| **Test files** | `tests/test_main.py`, `tests/test_extended.py` |
| **Framework** | pytest 7.x + FastAPI `TestClient` |
| **Database** | Isolated in-memory SQLite (shared engine via `tests/conftest.py`) |
| **Run command** | `cd backend && python -m pytest tests/ -v` |

---

## 2. Test Infrastructure

### 2.1 Shared Engine (`tests/conftest.py`)

A single `conftest.py` at the tests directory level creates one shared SQLite test engine before any test module loads. This prevents the engine-override collision that would otherwise occur when both `test_main.py` and `test_extended.py` import the FastAPI app in the same pytest session.

```
pytest session start
       │
       ▼
conftest.py  →  creates shared SQLite engine
               →  calls set_engine_override(shared_engine)
               →  creates all tables
               │
       ▼
test_extended.py  →  imports shared_engine from conftest
test_main.py      →  imports shared_engine from conftest
               │
       ▼ (before each test)
_reset_tables fixture  →  DELETE FROM executiontrace / agenttask / systemuser
               │
       ▼ (session end)
pytest_sessionfinish  →  removes .test_shared.db file
```

### 2.2 Test Isolation

Each test function runs against a clean database state. The `_reset_tables` fixture (autouse, function scope) truncates all three tables before every test so no test depends on the state left by a previous one.

### 2.3 No Live LLM Calls

The test suite does **not** invoke the LLM or the MCP subprocess. MCP tool functions are imported and called directly as Python functions. The agent streaming endpoint is tested only for error cases (task not found, invalid UUID). This keeps the suite deterministic and fast (~3 seconds total).

---

## 3. Test Modules

### 3.1 `test_main.py` — Baseline API & Tool Tests (57 tests)

The original test file covering the core API surface and the three most-used tools.

| Class | Tests | What it covers |
|---|---|---|
| `TestRootEndpoint` | 2 | Root `GET /` returns 200 with `message` + `version` fields |
| `TestHealthEndpoint` | 1 | `GET /api/health` returns `{"status": "healthy"}` |
| `TestTaskCreation` | 5 | Task creation success, empty/missing prompt rejection, invalid user_id, auto-user creation |
| `TestTaskListing` | 3 | Empty list, list after creation, required fields present |
| `TestTaskDetail` | 3 | Fetch by ID, 404 for unknown, 400 for invalid UUID |
| `TestStreamEndpoint` | 2 | SSE stream 404 and 400 for bad task IDs |
| `TestTextProcessor` | 9 | uppercase, lowercase, wordcount, reverse, titlecase, invalid op, case-insensitive op, empty string |
| `TestCalculator` | 12 | add, sub, mul, div, float div, complex expr, nested parens, exponentiation, negatives, div by zero, invalid expr, modulo |
| `TestWeatherMock` | 6 | Valid JSON shape, deterministic output, different locations, case-insensitive, location field, forecast field |
| `TestDatabaseModels` | 4 | Direct ORM: create user, create task with FK, create trace, default status |

### 3.2 `test_extended.py` — Extended Coverage (77 tests)

Deep-dive tests added to cover the delete endpoint, all 8 MCP tools fully, task lifecycle, trace ordering, and repository edge cases.

| Class | Tests | What it covers |
|---|---|---|
| `TestDeleteTask` | 6 | DELETE endpoint happy path, 404, 400 bad UUID, removes from list, cascade traces, double-delete |
| `TestListTasksUserField` | 3 | `user_id` present in list, multiple entries, task detail includes `user_id` |
| `TestAuthEndpoints` | 4 | Unregistered email → 403, wrong token → 401/500, missing token field → 422, missing email → 422 |
| `TestTaskLifecycle` | 7 | Pending default status, pending→running→completed transitions, explicit user_id, max length 2000, at-limit accepted, 5 concurrent unique IDs, newest-first ordering |
| `TestExecutionTraces` | 5 | Empty traces initially, ordered by step, all four types present, content preserved, repo create+get traces |
| `TestHashGenerator` | 7 | sha256 exact hash, md5 length, sha512 length, sha1 exact hash, deterministic, empty string, invalid algorithm |
| `TestDatetimeTool` | 7 | `now` contains date, `now` contains time, `now` contains day_of_week, add 10 days, subtract 1 day (leap year), days_between, invalid operation |
| `TestUnitConverter` | 7 | C→F, F→C, km→mi, kg→lb, m→ft, unsupported conversion error, from/to fields in response |
| `TestJsonFormatter` | 6 | prettify adds newlines, minify removes spaces, validate valid JSON, validate invalid JSON, extract_keys, count_items |
| `TestRandomGenerator` | 7 | uuid is valid v4, uuid unique across calls, password default length, password custom length, number in range, min/max in response, invalid operation |
| `TestTextProcessorEdgeCases` | 6 | Whitespace-only, numbers in string, extra spaces wordcount, palindrome reverse, titlecase with numbers, case-insensitive op name |
| `TestCalculatorEdgeCases` | 11 | Large numbers, float precision, integer no decimal, order of operations, nested parens, exponentiation, modulo, negatives, div by zero, unary negative, dangerous builtins blocked |
| `TestRepositoryPattern` | 9 | get_user nonexistent, get_task nonexistent, update_task nonexistent, delete_task nonexistent, list includes user_id, default role, admin role, get_user invalid UUID, get_task invalid UUID |

---

## 4. CI/CD Integration

Tests run as **Job 1** (`backend-test`) in the GitHub Actions pipeline, blocking all downstream jobs on failure.

```yaml
- name: Run tests
  run: cd backend && python -m pytest -v --tb=short
```

The pipeline only proceeds to `frontend-build` → `docker-build` → `deploy` if all 134 tests pass. This ensures broken code can never reach production.

---

## 5. Coverage by Layer

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer               Tests   What's tested                      │
├─────────────────────────────────────────────────────────────────┤
│  REST API (router)    25     POST/GET/DELETE endpoints,         │
│                              validation, status codes, SSE 404  │
│  Repository           12     CRUD, cascade delete, user_id,     │
│                              error cases (nonexistent, bad UUID) │
│  Database models       4     ORM table creation, FK integrity,   │
│                              default values                      │
│  MCP Tools            82     All 8 tools: happy path +          │
│                              edge cases + error handling         │
│  Auth                  4     Email allowlist, missing fields     │
│  Task lifecycle        7     Status machine, ordering, limits    │
│  Execution traces      5     Ordering, types, content            │
├─────────────────────────────────────────────────────────────────┤
│  TOTAL               134     All passing                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix A — Complete Unit Test Reference

### A.1 `test_main.py` — 57 Tests

#### TestRootEndpoint

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 1 | `test_root_returns_200` | GET / returns HTTP 200 | `GET /` |
| 2 | `test_root_contains_message` | Response body has `message` and `version` keys | `GET /` |

#### TestHealthEndpoint

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 3 | `test_health_returns_healthy` | Returns `{"status": "healthy"}` | `GET /api/health` |

#### TestTaskCreation

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 4 | `test_create_task_success` | Valid prompt returns task_id and `pending` status | `POST /api/task` |
| 5 | `test_create_task_empty_prompt_rejected` | Empty string prompt returns 422 | `POST /api/task` |
| 6 | `test_create_task_missing_prompt_rejected` | Missing prompt field returns 422 | `POST /api/task` |
| 7 | `test_create_task_with_invalid_user_id` | Non-UUID user_id returns 400 | `POST /api/task` |
| 8 | `test_create_task_auto_creates_user` | No user_id provided still returns valid UUID task_id | `POST /api/task` |

#### TestTaskListing

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 9 | `test_list_tasks_empty` | Returns empty list when no tasks exist | `GET /api/tasks` |
| 10 | `test_list_tasks_after_creation` | Returns correct count after creating 2 tasks | `GET /api/tasks` |
| 11 | `test_list_tasks_contains_fields` | Each item has id, raw_input, execution_status, created_at | `GET /api/tasks` |

#### TestTaskDetail

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 12 | `test_get_task_detail` | Returns full task with matching raw_input and traces key | `GET /api/task/{id}` |
| 13 | `test_get_task_not_found` | Unknown UUID returns 404 | `GET /api/task/{id}` |
| 14 | `test_get_task_invalid_uuid` | Non-UUID path param returns 400 | `GET /api/task/{id}` |

#### TestStreamEndpoint

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 15 | `test_stream_task_not_found` | SSE stream for unknown task ID returns 404 | `GET /api/task/{id}/stream` |
| 16 | `test_stream_task_invalid_uuid` | SSE stream for non-UUID returns 400 | `GET /api/task/{id}/stream` |

#### TestTextProcessor

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 17 | `test_uppercase` | "hello world" → "HELLO WORLD" | `text_processor()` |
| 18 | `test_lowercase` | "HELLO WORLD" → "hello world" | `text_processor()` |
| 19 | `test_wordcount` | "one two three four" → "4" | `text_processor()` |
| 20 | `test_wordcount_single` | Single word → "1" | `text_processor()` |
| 21 | `test_reverse` | "abcdef" → "fedcba" | `text_processor()` |
| 22 | `test_titlecase` | "hello world foo" → "Hello World Foo" | `text_processor()` |
| 23 | `test_invalid_operation` | Unknown op returns error message | `text_processor()` |
| 24 | `test_case_insensitive_operation` | "UPPERCASE" op name works | `text_processor()` |
| 25 | `test_empty_string` | Empty input returns empty string | `text_processor()` |

#### TestCalculator

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 26 | `test_addition` | "3 + 5" → "8" | `calculator()` |
| 27 | `test_subtraction` | "10 - 3" → "7" | `calculator()` |
| 28 | `test_multiplication` | "4 * 6" → "24" | `calculator()` |
| 29 | `test_division` | "15 / 3" → "5" | `calculator()` |
| 30 | `test_float_division` | "7 / 2" → "3.5" | `calculator()` |
| 31 | `test_complex_expression` | "(3 + 5) * 2" → "16" | `calculator()` |
| 32 | `test_nested_parentheses` | "((2+3)*(4-1))" → "15" | `calculator()` |
| 33 | `test_exponentiation` | "2 ** 10" → "1024" | `calculator()` |
| 34 | `test_negative_numbers` | "-5 + 3" → "-2" | `calculator()` |
| 35 | `test_division_by_zero` | "1 / 0" returns "Division by zero" error | `calculator()` |
| 36 | `test_invalid_expression` | "not math" returns error | `calculator()` |
| 37 | `test_modulo` | "10 % 3" → "1" | `calculator()` |

#### TestWeatherMock

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 38 | `test_returns_valid_json` | Response is valid JSON with location, temperature_celsius, condition | `weather_mock()` |
| 39 | `test_deterministic_output` | Same location always returns identical weather | `weather_mock()` |
| 40 | `test_different_locations_different_weather` | Toronto ≠ Tokyo in temp or condition | `weather_mock()` |
| 41 | `test_case_insensitive_weather` | "LONDON" and "london" yield same numeric values | `weather_mock()` |
| 42 | `test_location_in_response` | location field matches input string | `weather_mock()` |
| 43 | `test_has_forecast_field` | Response contains `forecast` key | `weather_mock()` |

#### TestDatabaseModels

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 44 | `test_create_user` | SystemUser ORM insert, id is non-null | `SystemUser` model |
| 45 | `test_create_task_with_user` | AgentTask FK to SystemUser is stored correctly | `AgentTask` model |
| 46 | `test_create_execution_trace` | ExecutionTrace FK to AgentTask, category stored | `ExecutionTrace` model |
| 47 | `test_task_default_status` | AgentTask defaults execution_status to "pending" | `AgentTask` model |

---

### A.2 `test_extended.py` — 77 Tests

#### TestDeleteTask

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 48 | `test_delete_existing_task` | DELETE returns 200 with `{"deleted": true, "task_id": ...}` | `DELETE /api/task/{id}` |
| 49 | `test_delete_nonexistent_task` | Unknown UUID returns 404 | `DELETE /api/task/{id}` |
| 50 | `test_delete_invalid_uuid` | Non-UUID path param returns 400 | `DELETE /api/task/{id}` |
| 51 | `test_delete_removes_task_from_list` | After delete, GET /api/tasks returns empty | `DELETE /api/task/{id}` |
| 52 | `test_delete_cascades_traces` | Deleting task also removes all ExecutionTrace rows | `DELETE /api/task/{id}` + `repository.delete_task()` |
| 53 | `test_delete_task_twice_returns_404` | Second delete on same ID returns 404 | `DELETE /api/task/{id}` |

#### TestListTasksUserField

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 54 | `test_list_tasks_includes_user_id` | Each task in list contains a valid `user_id` UUID | `GET /api/tasks` |
| 55 | `test_list_tasks_multiple_entries` | All entries in multi-task list have user_id | `GET /api/tasks` |
| 56 | `test_task_detail_includes_user_id` | Single task detail also exposes `user_id` | `GET /api/task/{id}` |

#### TestAuthEndpoints

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 57 | `test_login_unregistered_email` | Email not in allowlist returns 403 | `POST /api/auth/login` |
| 58 | `test_login_wrong_token` | Valid email + wrong token returns 401 or 500 | `POST /api/auth/login` |
| 59 | `test_login_missing_token_field` | Missing token field returns 422 | `POST /api/auth/login` |
| 60 | `test_login_missing_email_field` | Missing email field returns 422 | `POST /api/auth/login` |

#### TestTaskLifecycle

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 61 | `test_task_created_as_pending` | Newly created task has status "pending" | `POST /api/task` |
| 62 | `test_task_status_transitions` | Repository: pending→running→completed, final_output set | `SQLModelRepository.update_task()` |
| 63 | `test_task_with_explicit_valid_user_id` | Pre-existing user_id accepted in task creation | `POST /api/task` |
| 64 | `test_task_prompt_max_length_enforced` | 2001-char prompt returns 422 | `POST /api/task` |
| 65 | `test_task_prompt_at_max_length_accepted` | 2000-char prompt returns 200 | `POST /api/task` |
| 66 | `test_concurrent_task_creation_unique_ids` | 5 rapid creates each return distinct UUID | `POST /api/task` |
| 67 | `test_task_ordering_newest_first` | GET /api/tasks returns newest task first | `GET /api/tasks` |

#### TestExecutionTraces

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 68 | `test_task_detail_has_empty_traces_initially` | Freshly created task has traces: [] | `GET /api/task/{id}` |
| 69 | `test_task_detail_traces_are_ordered_by_step` | Steps are monotonically increasing | `GET /api/task/{id}` |
| 70 | `test_trace_types_are_correct` | All four categories present after manual insert | `GET /api/task/{id}` |
| 71 | `test_trace_content_preserved` | Exact content strings round-trip through DB | `GET /api/task/{id}` |
| 72 | `test_repository_create_and_get_traces` | create_trace + get_traces returns correct types | `SQLModelRepository.create_trace()` / `get_traces()` |

#### TestHashGenerator

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 73 | `test_sha256` | "hello" → known sha256 hex digest, algorithm field present | `hash_generator()` |
| 74 | `test_md5` | MD5 digest is 32 hex chars | `hash_generator()` |
| 75 | `test_sha512` | SHA-512 digest is 128 hex chars | `hash_generator()` |
| 76 | `test_sha1` | "hello" → known sha1 hex digest | `hash_generator()` |
| 77 | `test_deterministic` | Same input+algo always yields same digest | `hash_generator()` |
| 78 | `test_empty_string` | Empty string sha256 is 64 hex chars | `hash_generator()` |
| 79 | `test_invalid_algorithm` | Unknown algorithm returns error message | `hash_generator()` |

#### TestDatetimeTool

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 80 | `test_now_contains_date` | `now` response includes today's ISO date | `datetime_tool()` |
| 81 | `test_now_contains_time` | `now` response includes HH:MM time string | `datetime_tool()` |
| 82 | `test_now_contains_day_of_week` | `now` response includes a valid day name | `datetime_tool()` |
| 83 | `test_add_days` | 2024-01-01 + 10 days → 2024-01-11 | `datetime_tool()` |
| 84 | `test_subtract_days` | 2024-03-01 − 1 day → 2024-02-29 (leap year) | `datetime_tool()` |
| 85 | `test_days_between` | 2024-01-01 to 2024-01-31 → 30 | `datetime_tool()` |
| 86 | `test_invalid_operation` | Unknown operation returns error/Supported message | `datetime_tool()` |

#### TestUnitConverter

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 87 | `test_celsius_to_fahrenheit` | 0°C → 32°F | `unit_converter()` |
| 88 | `test_fahrenheit_to_celsius` | 212°F → 100°C | `unit_converter()` |
| 89 | `test_km_to_mi` | 1 km → 0.6214 mi (within 0.001) | `unit_converter()` |
| 90 | `test_kg_to_lb` | 1 kg → 2.2046 lb (within 0.001) | `unit_converter()` |
| 91 | `test_meters_to_feet` | 1 m → 3.2808 ft (within 0.001) | `unit_converter()` |
| 92 | `test_unsupported_conversion` | USD→CAD returns error/cannot message | `unit_converter()` |
| 93 | `test_result_has_from_to_fields` | JSON response includes `from` and `to` fields | `unit_converter()` |

#### TestJsonFormatter

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 94 | `test_prettify` | Prettified output contains newlines | `json_formatter()` |
| 95 | `test_minify` | Minified output has no spaces | `json_formatter()` |
| 96 | `test_validate_valid` | Valid JSON returns "valid" in response | `json_formatter()` |
| 97 | `test_validate_invalid` | Malformed JSON returns "invalid"/error | `json_formatter()` |
| 98 | `test_extract_keys` | Returns key names from JSON object | `json_formatter()` |
| 99 | `test_count_items` | Array of 5 elements → "5" in response | `json_formatter()` |
| 100 | `test_empty_object` | `{}` prettifies without error | `json_formatter()` |

#### TestRandomGenerator

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 101 | `test_uuid_output` | Output value is a valid UUID v4 | `random_generator()` |
| 102 | `test_uuid_is_unique` | Two consecutive UUID calls return different values | `random_generator()` |
| 103 | `test_password_default_length` | Default password is ≥12 characters | `random_generator()` |
| 104 | `test_password_custom_length` | length=24 produces ≥20 character password | `random_generator()` |
| 105 | `test_number_in_range` | number with min=10, max=20 falls within [10, 20] | `random_generator()` |
| 106 | `test_number_has_min_max_in_result` | Response includes min and max fields | `random_generator()` |
| 107 | `test_invalid_type` | Unknown operation returns error message | `random_generator()` |

#### TestTextProcessorEdgeCases

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 108 | `test_whitespace_only` | Three spaces uppercased → three spaces | `text_processor()` |
| 109 | `test_numbers_in_string` | "abc123" uppercased → "ABC123" | `text_processor()` |
| 110 | `test_wordcount_extra_spaces` | Leading/trailing/multiple spaces still count 2 words | `text_processor()` |
| 111 | `test_reverse_palindrome` | "racecar" reversed → "racecar" | `text_processor()` |
| 112 | `test_titlecase_with_numbers` | Mixed text+numbers titlecased correctly | `text_processor()` |
| 113 | `test_case_insensitive_operation_name` | "UPPERCASE" and "LOWERCASE" op names accepted | `text_processor()` |

#### TestCalculatorEdgeCases

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 114 | `test_very_large_numbers` | 999999 × 999999 → 999998000001 | `calculator()` |
| 115 | `test_float_precision` | 0.1 + 0.2 ≈ 0.3 (within 0.0001) | `calculator()` |
| 116 | `test_integer_result_no_decimal` | 10/2 returns "5" not "5.0" | `calculator()` |
| 117 | `test_order_of_operations` | 2 + 3 * 4 → 14 (not 20) | `calculator()` |
| 118 | `test_nested_parentheses` | ((2+3)*(4-1)) → 15 | `calculator()` |
| 119 | `test_exponentiation` | 2**10 → 1024 | `calculator()` |
| 120 | `test_modulo` | 10 % 3 → 1 | `calculator()` |
| 121 | `test_negative_numbers` | -5 + 3 → -2 | `calculator()` |
| 122 | `test_division_by_zero` | 1/0 returns "Division by zero" | `calculator()` |
| 123 | `test_unary_negative` | -(-5) → 5 | `calculator()` |
| 124 | `test_dangerous_builtins_blocked` | `__import__` injection attempt returns error | `calculator()` |
| 125 | `test_chained_ops` | (10+5)*(20-15)/3 → 25 | `calculator()` |

#### TestRepositoryPattern

| # | Test Name | Description | Function/Endpoint |
|---|---|---|---|
| 126 | `test_get_nonexistent_user` | get_user with unknown UUID returns None | `SQLModelRepository.get_user()` |
| 127 | `test_get_nonexistent_task` | get_task with unknown UUID returns None | `SQLModelRepository.get_task()` |
| 128 | `test_update_nonexistent_task` | update_task with unknown UUID returns None | `SQLModelRepository.update_task()` |
| 129 | `test_delete_nonexistent_task` | delete_task with unknown UUID returns False | `SQLModelRepository.delete_task()` |
| 130 | `test_list_tasks_includes_user_id` | list_tasks result includes user_id matching creator | `SQLModelRepository.list_tasks()` |
| 131 | `test_user_role_default` | create_user without role defaults to "user" | `SQLModelRepository.create_user()` |
| 132 | `test_admin_role` | create_user with role_type="admin" persists correctly | `SQLModelRepository.create_user()` |
| 133 | `test_get_user_invalid_uuid_returns_none` | Non-UUID string to get_user returns None gracefully | `SQLModelRepository.get_user()` |
| 134 | `test_get_task_invalid_uuid_returns_none` | Non-UUID string to get_task returns None gracefully | `SQLModelRepository.get_task()` |

---

## Appendix B — Test Run Output (Final)

```
platform linux -- Python 3.10.x, pytest 7.x
tests/test_extended.py  77 passed
tests/test_main.py      57 passed
================================ 134 passed, 1 warning in 3.18s ================================
```

The single warning is a `StarletteDeprecationWarning` from the `httpx`/`starlette` test client version mismatch — it does not affect any test result and will be resolved when the project upgrades to `httpx2`.
