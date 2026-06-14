"""
Comprehensive test suite for the Agentic Execution Framework backend.

Tests cover:
  - API endpoints (root, health, task CRUD, validation)
  - MCP tool implementations (text_processor, calculator, weather_mock)
  - Database model creation and relationships
  - Error handling and edge cases

Run:  cd backend && pytest -v
"""

import json
import sys
import uuid
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, text

# ---------------------------------------------------------------------------
# Ensure imports work regardless of working directory
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
sys.path.insert(0, str(BACKEND_DIR))
MCP_DIR = BACKEND_DIR.parent / "mcp_server"
sys.path.insert(0, str(MCP_DIR))

from models import AgentTask, ExecutionTrace, SystemUser  # noqa: E402

# ---------------------------------------------------------------------------
# Test database setup — file-based SQLite to survive lifespan teardown
# ---------------------------------------------------------------------------
import tempfile, os  # noqa: E402
_test_db_file = os.path.join(BACKEND_DIR, ".test.db")
TEST_DATABASE_URL = f"sqlite:///{_test_db_file}"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})

# Override the engine BEFORE importing the app so lifespan uses test engine
from database import set_engine_override  # noqa: E402
set_engine_override(test_engine)

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    """Ensure tables exist and are empty before each test."""
    SQLModel.metadata.create_all(test_engine)
    yield
    # Clean all data after each test
    with Session(test_engine) as session:
        session.exec(text("DELETE FROM executiontrace"))
        session.exec(text("DELETE FROM agenttask"))
        session.exec(text("DELETE FROM systemuser"))
        session.commit()


def teardown_module():
    """Remove the test database file after all tests complete."""
    if os.path.exists(_test_db_file):
        os.unlink(_test_db_file)


client = TestClient(app)


# ===========================================================================
# 1. API Endpoint Tests
# ===========================================================================

class TestRootEndpoint:
    def test_root_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_contains_message(self):
        data = client.get("/").json()
        assert "message" in data
        assert "version" in data


class TestHealthEndpoint:
    def test_health_returns_healthy(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestTaskCreation:
    def test_create_task_success(self):
        response = client.post("/api/task", json={"prompt": "What is 2 + 2?"})
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    def test_create_task_empty_prompt_rejected(self):
        response = client.post("/api/task", json={"prompt": ""})
        assert response.status_code == 422  # Validation error

    def test_create_task_missing_prompt_rejected(self):
        response = client.post("/api/task", json={})
        assert response.status_code == 422

    def test_create_task_with_invalid_user_id(self):
        response = client.post("/api/task", json={"prompt": "test", "user_id": "not-a-uuid"})
        assert response.status_code == 400

    def test_create_task_auto_creates_user(self):
        response = client.post("/api/task", json={"prompt": "test task"})
        assert response.status_code == 200
        data = response.json()
        assert uuid.UUID(data["task_id"])


class TestTaskListing:
    def test_list_tasks_empty(self):
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_tasks_after_creation(self):
        client.post("/api/task", json={"prompt": "Task 1"})
        client.post("/api/task", json={"prompt": "Task 2"})
        response = client.get("/api/tasks")
        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) == 2

    def test_list_tasks_contains_fields(self):
        client.post("/api/task", json={"prompt": "Field check"})
        tasks = client.get("/api/tasks").json()
        assert len(tasks) == 1
        task = tasks[0]
        assert "id" in task
        assert "raw_input" in task
        assert "execution_status" in task
        assert "created_at" in task


class TestTaskDetail:
    def test_get_task_detail(self):
        create_resp = client.post("/api/task", json={"prompt": "Detail test"})
        task_id = create_resp.json()["task_id"]
        response = client.get(f"/api/task/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["raw_input"] == "Detail test"
        assert "traces" in data

    def test_get_task_not_found(self):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/task/{fake_id}")
        assert response.status_code == 404

    def test_get_task_invalid_uuid(self):
        response = client.get("/api/task/not-a-uuid")
        assert response.status_code == 400


class TestStreamEndpoint:
    def test_stream_task_not_found(self):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/task/{fake_id}/stream")
        assert response.status_code == 404

    def test_stream_task_invalid_uuid(self):
        response = client.get("/api/task/invalid/stream")
        assert response.status_code == 400


# ===========================================================================
# 2. MCP Tool Tests (direct function calls, no MCP transport needed)
# ===========================================================================

from mcp_server import text_processor, calculator, weather_mock  # noqa: E402


class TestTextProcessor:
    def test_uppercase(self):
        assert text_processor("hello world", "uppercase") == "HELLO WORLD"

    def test_lowercase(self):
        assert text_processor("HELLO WORLD", "lowercase") == "hello world"

    def test_wordcount(self):
        assert text_processor("one two three four", "wordcount") == "4"

    def test_wordcount_single(self):
        assert text_processor("hello", "wordcount") == "1"

    def test_reverse(self):
        assert text_processor("abcdef", "reverse") == "fedcba"

    def test_titlecase(self):
        assert text_processor("hello world foo", "titlecase") == "Hello World Foo"

    def test_invalid_operation(self):
        result = text_processor("hello", "explode")
        assert "Invalid operation" in result

    def test_case_insensitive_operation(self):
        assert text_processor("hello", "UPPERCASE") == "HELLO"

    def test_empty_string(self):
        assert text_processor("", "uppercase") == ""


class TestCalculator:
    def test_addition(self):
        assert calculator("3 + 5") == "8"

    def test_subtraction(self):
        assert calculator("10 - 3") == "7"

    def test_multiplication(self):
        assert calculator("4 * 6") == "24"

    def test_division(self):
        assert calculator("15 / 3") == "5"

    def test_float_division(self):
        assert calculator("7 / 2") == "3.5"

    def test_complex_expression(self):
        assert calculator("(3 + 5) * 2") == "16"

    def test_nested_parentheses(self):
        assert calculator("((2 + 3) * (4 - 1))") == "15"

    def test_exponentiation(self):
        assert calculator("2 ** 10") == "1024"

    def test_negative_numbers(self):
        assert calculator("-5 + 3") == "-2"

    def test_division_by_zero(self):
        result = calculator("1 / 0")
        assert "Division by zero" in result

    def test_invalid_expression(self):
        result = calculator("not math")
        assert "Error" in result

    def test_modulo(self):
        assert calculator("10 % 3") == "1"


class TestWeatherMock:
    def test_returns_valid_json(self):
        result = weather_mock("Toronto")
        data = json.loads(result)
        assert "location" in data
        assert "temperature_celsius" in data
        assert "condition" in data

    def test_deterministic_output(self):
        """Same location should always return the same weather."""
        r1 = json.loads(weather_mock("New York"))
        r2 = json.loads(weather_mock("New York"))
        assert r1 == r2

    def test_different_locations_different_weather(self):
        r1 = json.loads(weather_mock("Toronto"))
        r2 = json.loads(weather_mock("Tokyo"))
        assert r1["temperature_celsius"] != r2["temperature_celsius"] or r1["condition"] != r2["condition"]

    def test_case_insensitive_weather(self):
        """Hash is case-insensitive; numeric values should match regardless of input casing."""
        r1 = json.loads(weather_mock("LONDON"))
        r2 = json.loads(weather_mock("london"))
        assert r1["temperature_celsius"] == r2["temperature_celsius"]
        assert r1["condition"] == r2["condition"]

    def test_location_in_response(self):
        data = json.loads(weather_mock("Paris"))
        assert data["location"] == "Paris"

    def test_has_forecast_field(self):
        data = json.loads(weather_mock("Berlin"))
        assert "forecast" in data


# ===========================================================================
# 3. Database Model Tests
# ===========================================================================

class TestDatabaseModels:
    def test_create_user(self):
        with Session(test_engine) as session:
            user = SystemUser(username="testuser", role_type="admin")
            session.add(user)
            session.commit()
            session.refresh(user)
            assert user.id is not None
            assert user.username == "testuser"

    def test_create_task_with_user(self):
        with Session(test_engine) as session:
            user = SystemUser(username="agent_user", role_type="user")
            session.add(user)
            session.commit()
            session.refresh(user)

            task = AgentTask(
                user_id=user.id,
                raw_input="Calculate 2+2",
                execution_status="pending",
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            assert task.id is not None
            assert task.user_id == user.id

    def test_create_execution_trace(self):
        with Session(test_engine) as session:
            user = SystemUser(username="trace_user", role_type="user")
            session.add(user)
            session.commit()
            session.refresh(user)

            task = AgentTask(user_id=user.id, raw_input="test", execution_status="running")
            session.add(task)
            session.commit()
            session.refresh(task)

            trace = ExecutionTrace(
                task_id=task.id,
                sequence_step=0,
                action_category="thought",
                payload_content="Thinking about the request...",
            )
            session.add(trace)
            session.commit()
            session.refresh(trace)

            assert trace.id is not None
            assert trace.task_id == task.id
            assert trace.action_category == "thought"

    def test_task_default_status(self):
        """AgentTask should default to 'pending' execution_status."""
        with Session(test_engine) as session:
            user = SystemUser(username="default_status_user", role_type="user")
            session.add(user)
            session.commit()
            session.refresh(user)

            task = AgentTask(user_id=user.id, raw_input="test defaults")
            session.add(task)
            session.commit()
            session.refresh(task)
            assert task.execution_status == "pending"
