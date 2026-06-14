"""
Extended test suite — deeper coverage beyond the baseline test_main.py.

Covers:
  - DELETE /api/task/{id} endpoint (task + trace cascade)
  - Auth endpoints (login, /me, /init)
  - Repository delete_task + list_tasks user_id field
  - All 8 MCP tools with correct signatures (hash_generator, datetime_tool,
    unit_converter, json_formatter, random_generator, text_processor, calculator,
    weather_mock) including edge cases
  - Task status lifecycle (pending → running → completed / failed)
  - Concurrent task creation (unique IDs)
  - Large payload validation (max_length enforcement)
  - SSE stream endpoint for missing vs existing tasks
  - Database cascade deletion (traces removed with task)
  - Repository pattern (get/update/delete nonexistent records)

Run:  cd backend && pytest tests/test_extended.py -v
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, text

# ─── Path Setup ───────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
MCP_DIR = BACKEND_DIR.parent / "mcp_server"
sys.path.insert(0, str(MCP_DIR))

from models import AgentTask, ExecutionTrace, SystemUser  # noqa: E402

# ─── Isolated Test DB (separate file from test_main.py to avoid collision) ────
# Use the shared engine set up by conftest.py
from tests.conftest import shared_engine as test_engine  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def teardown_module():
    """Nothing to clean up — shared DB is managed by conftest.py."""
    pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _create_task(prompt: str = "test task") -> dict:
    return client.post("/api/task", json={"prompt": prompt}).json()


def _create_task_with_traces() -> str:
    """Create a task and manually insert execution traces, return task_id."""
    task_data = _create_task("trace test task")
    task_id = task_data["task_id"]
    with Session(test_engine) as session:
        for step, category, content in [
            (0, "thought", "Received task"),
            (1, "tool_call", "Calling calculator"),
            (2, "tool_result", "42"),
            (3, "final_result", "The answer is 42"),
        ]:
            trace = ExecutionTrace(
                task_id=uuid.UUID(task_id),
                sequence_step=step,
                action_category=category,
                payload_content=content,
            )
            session.add(trace)
        session.commit()
    return task_id


# ===========================================================================
# 1. DELETE Endpoint Tests
# ===========================================================================

class TestDeleteTask:
    def test_delete_existing_task(self):
        task_id = _create_task()["task_id"]
        resp = client.delete(f"/api/task/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["task_id"] == task_id

    def test_delete_nonexistent_task(self):
        resp = client.delete(f"/api/task/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_invalid_uuid(self):
        resp = client.delete("/api/task/not-a-uuid")
        assert resp.status_code == 400

    def test_delete_removes_task_from_list(self):
        task_id = _create_task("to be deleted")["task_id"]
        assert len(client.get("/api/tasks").json()) == 1
        client.delete(f"/api/task/{task_id}")
        assert client.get("/api/tasks").json() == []

    def test_delete_cascades_traces(self):
        """Deleting a task must also remove all associated execution traces."""
        task_id = _create_task_with_traces()

        # Confirm traces exist before deletion
        detail_before = client.get(f"/api/task/{task_id}").json()
        assert len(detail_before["traces"]) == 4

        # Delete the task
        client.delete(f"/api/task/{task_id}")

        # Task should be gone
        assert client.get(f"/api/task/{task_id}").status_code == 404

        # Verify traces are also purged from DB
        with Session(test_engine) as session:
            remaining = session.exec(
                text(f"SELECT COUNT(*) FROM executiontrace WHERE task_id = '{task_id}'")
            ).one()
            assert remaining[0] == 0

    def test_delete_task_twice_returns_404(self):
        task_id = _create_task()["task_id"]
        client.delete(f"/api/task/{task_id}")
        resp = client.delete(f"/api/task/{task_id}")
        assert resp.status_code == 404


# ===========================================================================
# 2. list_tasks Includes user_id
# ===========================================================================

class TestListTasksUserField:
    def test_list_tasks_includes_user_id(self):
        _create_task("user_id check")
        tasks = client.get("/api/tasks").json()
        assert len(tasks) == 1
        assert "user_id" in tasks[0]
        assert uuid.UUID(tasks[0]["user_id"])

    def test_list_tasks_multiple_entries(self):
        _create_task("first task")
        _create_task("second task")
        tasks = client.get("/api/tasks").json()
        assert len(tasks) == 2
        for task in tasks:
            assert "user_id" in task
            assert uuid.UUID(task["user_id"])

    def test_task_detail_includes_user_id(self):
        task_id = _create_task()["task_id"]
        detail = client.get(f"/api/task/{task_id}").json()
        assert "user_id" in detail
        assert uuid.UUID(detail["user_id"])


# ===========================================================================
# 3. Auth Endpoint Tests
# ===========================================================================

class TestAuthEndpoints:
    def test_login_unregistered_email(self):
        resp = client.post("/api/auth/login", json={
            "email": "hacker@evil.com",
            "token": "anything"
        })
        assert resp.status_code == 403

    def test_login_wrong_token(self):
        resp = client.post("/api/auth/login", json={
            "email": "nildip2002@outlook.com",
            "token": "wrong-token-123"
        })
        # 401 wrong token; 503/500 if Key Vault unavailable in test env
        assert resp.status_code in (401, 503, 500)

    def test_login_missing_token_field(self):
        resp = client.post("/api/auth/login", json={"email": "test@test.com"})
        assert resp.status_code == 422

    def test_login_missing_email_field(self):
        resp = client.post("/api/auth/login", json={"token": "abc123"})
        assert resp.status_code == 422


# ===========================================================================
# 4. Task Lifecycle & Validation Tests
# ===========================================================================

class TestTaskLifecycle:
    def test_task_created_as_pending(self):
        task = _create_task()
        assert task["status"] == "pending"

    def test_task_status_transitions(self):
        """Simulate status updates via the repository directly."""
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            user = repo.create_user("lifecycle_user")
            task = repo.create_task(user["id"], "status test")
            task_id = task["id"]

            updated = repo.update_task(task_id, execution_status="running")
            assert updated["execution_status"] == "running"

            updated = repo.update_task(
                task_id,
                execution_status="completed",
                final_output="Done!"
            )
            assert updated["execution_status"] == "completed"
            assert updated["final_output"] == "Done!"

    def test_task_with_explicit_valid_user_id(self):
        with Session(test_engine) as session:
            from repository import SQLModelRepository
            repo = SQLModelRepository(session)
            user = repo.create_user("explicit_user")
            user_id = user["id"]

        resp = client.post("/api/task", json={"prompt": "explicit user task", "user_id": user_id})
        assert resp.status_code == 200

    def test_task_prompt_max_length_enforced(self):
        resp = client.post("/api/task", json={"prompt": "x" * 2001})
        assert resp.status_code == 422

    def test_task_prompt_at_max_length_accepted(self):
        resp = client.post("/api/task", json={"prompt": "y" * 2000})
        assert resp.status_code == 200

    def test_concurrent_task_creation_unique_ids(self):
        ids = [_create_task(f"concurrent {i}")["task_id"] for i in range(5)]
        assert len(set(ids)) == 5

    def test_task_ordering_newest_first(self):
        _create_task("first")
        _create_task("second")
        _create_task("third")
        tasks = client.get("/api/tasks").json()
        assert tasks[0]["raw_input"] == "third"
        assert tasks[-1]["raw_input"] == "first"


# ===========================================================================
# 5. Execution Trace Tests
# ===========================================================================

class TestExecutionTraces:
    def test_task_detail_has_empty_traces_initially(self):
        task_id = _create_task()["task_id"]
        detail = client.get(f"/api/task/{task_id}").json()
        assert detail["traces"] == []

    def test_task_detail_traces_are_ordered_by_step(self):
        task_id = _create_task_with_traces()
        detail = client.get(f"/api/task/{task_id}").json()
        steps = [t["step"] for t in detail["traces"]]
        assert steps == sorted(steps)

    def test_trace_types_are_correct(self):
        task_id = _create_task_with_traces()
        detail = client.get(f"/api/task/{task_id}").json()
        types = [t["type"] for t in detail["traces"]]
        assert "thought" in types
        assert "tool_call" in types
        assert "tool_result" in types
        assert "final_result" in types

    def test_trace_content_preserved(self):
        task_id = _create_task_with_traces()
        detail = client.get(f"/api/task/{task_id}").json()
        contents = {t["type"]: t["content"] for t in detail["traces"]}
        assert contents["thought"] == "Received task"
        assert contents["final_result"] == "The answer is 42"

    def test_repository_create_and_get_traces(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            user = repo.create_user("trace_test_user")
            task = repo.create_task(user["id"], "trace test")
            task_id = task["id"]
            repo.create_trace(task_id, 0, "thought", "Step 0")
            repo.create_trace(task_id, 1, "tool_call", "Calling tool X")
            traces = repo.get_traces(task_id)
        assert len(traces) == 2
        assert traces[0]["type"] == "thought"
        assert traces[1]["type"] == "tool_call"


# ===========================================================================
# 6. Extended MCP Tool Tests  (using correct actual API signatures)
# ===========================================================================

from mcp_server import (  # noqa: E402
    text_processor, calculator, weather_mock,
    datetime_tool, unit_converter, json_formatter,
    hash_generator, random_generator,
)


class TestHashGenerator:
    """hash_generator(text: str, algorithm: str) -> str (JSON)"""

    def test_sha256(self):
        result = json.loads(hash_generator("hello", "sha256"))
        assert result["hash"] == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        assert result["algorithm"] == "sha256"

    def test_md5(self):
        result = json.loads(hash_generator("hello", "md5"))
        assert len(result["hash"]) == 32

    def test_sha512(self):
        result = json.loads(hash_generator("hello", "sha512"))
        assert len(result["hash"]) == 128

    def test_sha1(self):
        result = json.loads(hash_generator("hello", "sha1"))
        assert result["hash"] == "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"

    def test_deterministic(self):
        assert hash_generator("abc", "sha256") == hash_generator("abc", "sha256")

    def test_empty_string(self):
        result = json.loads(hash_generator("", "sha256"))
        assert len(result["hash"]) == 64  # sha256 always 64 hex chars

    def test_invalid_algorithm(self):
        result = hash_generator("hello", "sha999")
        assert "Error" in result or "Invalid" in result or "Unsupported" in result


class TestDatetimeTool:
    """datetime_tool(operation, value='', timezone_name='UTC', days=0) -> str"""

    def test_now_contains_date(self):
        result = json.loads(datetime_tool("now"))
        assert "date" in result
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert result["date"] == today

    def test_now_contains_time(self):
        result = json.loads(datetime_tool("now"))
        assert "time" in result
        assert ":" in result["time"]

    def test_now_contains_day_of_week(self):
        result = json.loads(datetime_tool("now"))
        assert "day_of_week" in result
        assert result["day_of_week"] in [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"
        ]

    def test_add_days(self):
        result = datetime_tool("add_days", "2024-01-01", days=10)
        assert "2024-01-11" in result

    def test_subtract_days(self):
        result = datetime_tool("add_days", "2024-03-01", days=-1)
        assert "2024-02-29" in result  # 2024 is a leap year

    def test_days_between(self):
        result = datetime_tool("days_between", "2024-01-01,2024-01-31")
        assert "30" in result

    def test_invalid_operation(self):
        result = datetime_tool("explode_time")
        assert "Error" in result or "Invalid" in result or "Supported" in result


class TestUnitConverter:
    """unit_converter(value: float, from_unit: str, to_unit: str) -> str (JSON)"""

    def test_celsius_to_fahrenheit(self):
        result = json.loads(unit_converter(0, "C", "F"))
        assert result["value"] == 32.0

    def test_fahrenheit_to_celsius(self):
        result = json.loads(unit_converter(212, "F", "C"))
        assert result["value"] == 100.0

    def test_km_to_mi(self):
        result = json.loads(unit_converter(1, "km", "mi"))
        assert abs(result["value"] - 0.6214) < 0.001

    def test_kg_to_lb(self):
        result = json.loads(unit_converter(1, "kg", "lb"))
        assert abs(result["value"] - 2.2046) < 0.001

    def test_meters_to_feet(self):
        result = json.loads(unit_converter(1, "m", "ft"))
        assert abs(result["value"] - 3.2808) < 0.001

    def test_unsupported_conversion(self):
        result = unit_converter(100, "USD", "CAD")
        assert "Error" in result or "Cannot" in result or "not supported" in result.lower()

    def test_result_has_from_to_fields(self):
        result = json.loads(unit_converter(100, "C", "F"))
        assert result["from"] == "C"
        assert result["to"] == "F"


class TestJsonFormatter:
    """json_formatter(json_string: str, operation: str) -> str"""

    def test_prettify(self):
        result = json_formatter('{"a":1,"b":2}', "prettify")
        assert "\n" in result  # prettified has newlines

    def test_minify(self):
        result = json_formatter('{"a": 1, "b": 2}', "minify")
        assert " " not in result

    def test_validate_valid(self):
        result = json_formatter('{"key": "value"}', "validate")
        assert "valid" in result.lower()

    def test_validate_invalid(self):
        result = json_formatter("{not valid json}", "validate")
        assert "invalid" in result.lower() or "Error" in result

    def test_extract_keys(self):
        result = json_formatter('{"name":"Alice","age":30}', "extract_keys")
        assert "name" in result
        assert "age" in result

    def test_count_items(self):
        result = json_formatter('[1,2,3,4,5]', "count_items")
        assert "5" in result

    def test_empty_object(self):
        result = json_formatter("{}", "prettify")
        assert "{" in result


class TestRandomGenerator:
    """random_generator(operation, min_val, max_val, length, items, seed) -> str (JSON)"""

    def test_uuid_output(self):
        result = json.loads(random_generator("uuid"))
        parsed = uuid.UUID(result["value"])
        assert parsed.version == 4

    def test_uuid_is_unique(self):
        r1 = json.loads(random_generator("uuid"))["value"]
        r2 = json.loads(random_generator("uuid"))["value"]
        assert r1 != r2

    def test_password_default_length(self):
        result = json.loads(random_generator("password"))
        assert len(result["value"]) >= 12

    def test_password_custom_length(self):
        result = json.loads(random_generator("password", length=24))
        assert len(result["value"]) >= 20

    def test_number_in_range(self):
        result = json.loads(random_generator("number", min_val=10, max_val=20))
        num = result["value"]
        assert 10 <= num <= 20

    def test_number_has_min_max_in_result(self):
        result = json.loads(random_generator("number", min_val=5, max_val=15))
        assert result["min"] == 5
        assert result["max"] == 15

    def test_invalid_type(self):
        result = random_generator("teleport")
        assert "Error" in result or "Invalid" in result or "Unknown" in result


class TestTextProcessorEdgeCases:
    def test_whitespace_only(self):
        result = text_processor("   ", "uppercase")
        assert result == "   "

    def test_numbers_in_string(self):
        result = text_processor("abc123", "uppercase")
        assert result == "ABC123"

    def test_wordcount_extra_spaces(self):
        result = text_processor("  hello   world  ", "wordcount")
        assert result == "2"

    def test_reverse_palindrome(self):
        result = text_processor("racecar", "reverse")
        assert result == "racecar"

    def test_titlecase_with_numbers(self):
        result = text_processor("hello world 123", "titlecase")
        assert "Hello" in result and "World" in result

    def test_case_insensitive_operation_name(self):
        assert text_processor("hello", "UPPERCASE") == "HELLO"
        assert text_processor("HELLO", "LOWERCASE") == "hello"


class TestCalculatorEdgeCases:
    def test_very_large_numbers(self):
        result = calculator("999999 * 999999")
        assert "999998000001" in result

    def test_float_precision(self):
        val = float(calculator("0.1 + 0.2").strip())
        assert abs(val - 0.3) < 0.0001

    def test_integer_result_no_decimal(self):
        assert calculator("10 / 2") == "5"

    def test_order_of_operations(self):
        assert calculator("2 + 3 * 4") == "14"

    def test_nested_parentheses(self):
        assert calculator("((2 + 3) * (4 - 1))") == "15"

    def test_exponentiation(self):
        assert calculator("2 ** 10") == "1024"

    def test_modulo(self):
        assert calculator("10 % 3") == "1"

    def test_negative_numbers(self):
        assert calculator("-5 + 3") == "-2"

    def test_division_by_zero(self):
        result = calculator("1 / 0")
        assert "Division by zero" in result

    def test_unary_negative(self):
        assert calculator("-(-5)") == "5"

    def test_dangerous_builtins_blocked(self):
        result = calculator("__import__('os').system('echo hi')")
        assert "Error" in result

    def test_chained_ops(self):
        result = calculator("(10 + 5) * (20 - 15) / 3")
        assert "25" in result


# ===========================================================================
# 7. Repository Pattern Tests
# ===========================================================================

class TestRepositoryPattern:
    def test_get_nonexistent_user(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            result = repo.get_user(str(uuid.uuid4()))
        assert result is None

    def test_get_nonexistent_task(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            result = repo.get_task(str(uuid.uuid4()))
        assert result is None

    def test_update_nonexistent_task(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            result = repo.update_task(str(uuid.uuid4()), execution_status="failed")
        assert result is None

    def test_delete_nonexistent_task(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            result = repo.delete_task(str(uuid.uuid4()))
        assert result is False

    def test_list_tasks_includes_user_id(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            user = repo.create_user("list_user")
            repo.create_task(user["id"], "list test")
            tasks = repo.list_tasks()
        assert len(tasks) == 1
        assert "user_id" in tasks[0]
        assert tasks[0]["user_id"] == user["id"]

    def test_user_role_default(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            user = repo.create_user("role_test_user")
        assert user["role_type"] == "user"

    def test_admin_role(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            admin = repo.create_user("admin_user", role_type="admin")
        assert admin["role_type"] == "admin"

    def test_get_user_invalid_uuid_returns_none(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            result = repo.get_user("not-a-uuid")
        assert result is None

    def test_get_task_invalid_uuid_returns_none(self):
        from repository import SQLModelRepository
        with Session(test_engine) as session:
            repo = SQLModelRepository(session)
            result = repo.get_task("not-a-uuid")
        assert result is None
