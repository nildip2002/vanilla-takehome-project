"""Generate architecture diagrams using the Python `diagrams` library."""

import os
import sys

from diagrams import Cluster, Diagram, Edge
from diagrams.azure.compute import ContainerApps
from diagrams.azure.database import CosmosDb
from diagrams.azure.devops import Repos
from diagrams.azure.identity import ManagedIdentities
from diagrams.azure.integration import APIManagement
from diagrams.azure.ml import CognitiveServices
from diagrams.azure.monitor import ApplicationInsights
from diagrams.azure.web import AppServices
from diagrams.generic.device import Mobile, Tablet
from diagrams.onprem.client import Users
from diagrams.onprem.container import Docker
from diagrams.programming.framework import React, FastAPI

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "diagrams")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def system_architecture():
    """Diagram 1: Full Azure system architecture."""
    with Diagram(
        "BMO Agent - System Architecture",
        filename=os.path.join(OUTPUT_DIR, "system_architecture"),
        show=False,
        direction="LR",
        graph_attr={"bgcolor": "white", "pad": "0.5"},
    ):
        user = Users("Browser")

        with Cluster("Azure Cloud"):
            frontend = AppServices("Static Web App\n(React SPA)")

            with Cluster("Container Apps"):
                backend = ContainerApps("FastAPI Backend")
                mcp = ContainerApps("MCP Tool Server\n(8 tools)")

            with Cluster("Data & AI"):
                foundry = CognitiveServices("AI Foundry\n(GPT-4.1-nano)")
                cosmos = CosmosDb("Cosmos DB\n(Free Tier)")

            insights = ApplicationInsights("Application\nInsights")

        user >> Edge(label="HTTPS") >> frontend
        frontend >> Edge(label="API calls") >> backend
        backend >> Edge(label="subprocess") >> mcp
        backend >> Edge(label="OpenAI SDK") >> foundry
        backend >> Edge(label="SDK") >> cosmos
        backend >> Edge(label="telemetry") >> insights


def cicd_pipeline():
    """Diagram 2: CI/CD pipeline flow."""
    with Diagram(
        "BMO Agent - CI/CD Pipeline",
        filename=os.path.join(OUTPUT_DIR, "cicd_pipeline"),
        show=False,
        direction="LR",
        graph_attr={"bgcolor": "white", "pad": "0.5"},
    ):
        dev = Users("Developer")
        github = Repos("GitHub\nActions")

        with Cluster("Build & Test"):
            pytest_job = Docker("pytest\n(Backend)")
            vite_job = React("Vite Build\n(Frontend)")
            docker_job = Docker("Docker Build\n(Buildx Cache)")

        with Cluster("Azure Deploy"):
            acr = Docker("Container\nRegistry")
            container_app = ContainerApps("Container Apps\n(Backend)")
            swa = AppServices("Static Web App\n(Frontend)")

        smoke = Users("Smoke Tests")

        dev >> Edge(label="git push") >> github
        github >> pytest_job
        github >> vite_job
        pytest_job >> docker_job
        vite_job >> docker_job
        docker_job >> Edge(label="push image") >> acr
        acr >> container_app
        docker_job >> swa
        container_app >> smoke


def agent_flow():
    """Diagram 3: ReAct loop execution flow."""
    with Diagram(
        "BMO Agent - ReAct Execution Flow",
        filename=os.path.join(OUTPUT_DIR, "agent_flow"),
        show=False,
        direction="TB",
        graph_attr={"bgcolor": "white", "pad": "0.5"},
    ):
        user = Users("User Task")

        with Cluster("Agent Controller"):
            receive = FastAPI("Receive Task")
            reason = CognitiveServices("LLM Reasoning\n(Think)")
            decide = APIManagement("Decision:\nTool or Answer?")

        with Cluster("MCP Tools (8)"):
            tools = ContainerApps("text_processor\ncalculator\nweather_mock\ndatetime_tool\nunit_converter\njson_formatter\nhash_generator\nrandom_generator")

        result = CosmosDb("Persist Traces\n& Result")
        stream = Mobile("SSE Stream\nto Frontend")

        user >> receive
        receive >> reason
        reason >> decide
        decide >> Edge(label="tool_call") >> tools
        tools >> Edge(label="result") >> reason
        decide >> Edge(label="final_answer") >> result
        result >> stream


if __name__ == "__main__":
    print("Generating system architecture diagram...")
    system_architecture()
    print("Generating CI/CD pipeline diagram...")
    cicd_pipeline()
    print("Generating agent flow diagram...")
    agent_flow()
    print(f"Done! Diagrams saved to {OUTPUT_DIR}/")
