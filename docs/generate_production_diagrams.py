"""Generate production multi-agent architecture diagrams using the Python `diagrams` library."""

import os

from diagrams import Cluster, Diagram, Edge
from diagrams.azure.compute import ContainerApps, FunctionApps, ACR, AKS
from diagrams.azure.database import CosmosDb
from diagrams.azure.identity import ActiveDirectory, ManagedIdentities, ConditionalAccess, Users as AzureUsers, EntraManagedIdentities
from diagrams.azure.integration import APIManagement, ServiceBus, EventGridTopics, LogicApps
from diagrams.azure.ml import CognitiveServices, AzureOpenAI
from diagrams.azure.monitor import ApplicationInsights
from diagrams.azure.network import ApplicationGateway, FrontDoors, CDNProfiles, Firewall, VirtualNetworks, PrivateEndpoint
from diagrams.azure.security import KeyVaults, Sentinel, MicrosoftDefenderForCloud
from diagrams.azure.web import AppServices
from diagrams.azure.analytics import LogAnalyticsWorkspaces
from diagrams.onprem.client import Users
from diagrams.onprem.container import Docker
from diagrams.generic.storage import Storage

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "diagrams")
os.makedirs(OUTPUT_DIR, exist_ok=True)

GRAPH_ATTR = {"bgcolor": "#0f172a", "fontcolor": "#e2e8f0", "pad": "0.8", "fontsize": "14"}
EDGE_ATTR = {"color": "#06b6d4", "fontcolor": "#94a3b8", "fontsize": "10"}
NODE_ATTR = {"fontcolor": "#e2e8f0"}


def production_system_architecture():
    """Full production multi-agent system with Azure services."""
    with Diagram(
        "Production Multi-Agent Architecture",
        filename=os.path.join(OUTPUT_DIR, "prod_system_architecture"),
        show=False,
        direction="TB",
        graph_attr={**GRAPH_ATTR, "dpi": "150"},
        edge_attr=EDGE_ATTR,
        node_attr=NODE_ATTR,
    ):
        users = Users("End Users")

        with Cluster("Edge & Identity", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#06b6d4"}):
            frontdoor = FrontDoors("Azure Front Door\n(CDN + WAF)")
            entra = ActiveDirectory("Microsoft Entra ID\n(Azure AD)")
            conditional = ConditionalAccess("Conditional Access\nPolicies")

        with Cluster("API Layer", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#f59e0b"}):
            apim = APIManagement("API Management\n(Rate Limiting + Auth)")
            appgw = ApplicationGateway("App Gateway\n(L7 Load Balancer)")

        with Cluster("Agent Compute (Container Apps)", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#10b981"}):
            planner = ContainerApps("Planner Agent\n(Orchestrator)")
            code_agent = ContainerApps("Code Agent")
            research_agent = ContainerApps("Research Agent")
            data_agent = ContainerApps("Data Agent")
            qa_agent = ContainerApps("QA Agent")
            devops_agent = ContainerApps("DevOps Agent")
            cicd_agent = ContainerApps("CI/CD Agent")

        with Cluster("AI & LLM Layer", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#8b5cf6"}):
            foundry = AzureOpenAI("Azure AI Foundry\n(GPT-4o / 4.1-nano)")
            content_safety = CognitiveServices("Content Safety\n(Guardrails)")
            ai_search = CognitiveServices("Azure AI Search\n(RAG)")

        with Cluster("Messaging & Orchestration", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#ec4899"}):
            servicebus = ServiceBus("Service Bus\n(Agent Task Queue)")
            eventgrid = EventGridTopics("Event Grid\n(Agent Events)")
            durable = FunctionApps("Durable Functions\n(Saga/Workflow)")

        with Cluster("Data Layer", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#06b6d4"}):
            cosmos = CosmosDb("Cosmos DB\n(Tasks + Events)")
            redis = Storage("Azure Cache\nfor Redis")

        with Cluster("Security & Observability", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#f43f5e"}):
            keyvault = KeyVaults("Key Vault\n(Secrets + Certs)")
            sentinel = Sentinel("Microsoft Sentinel\n(SIEM)")
            defender = MicrosoftDefenderForCloud("Defender for Cloud")
            appinsights = ApplicationInsights("App Insights\n(Distributed Tracing)")
            loganalytics = LogAnalyticsWorkspaces("Log Analytics")

        # User flow
        users >> Edge(label="HTTPS") >> frontdoor
        frontdoor >> entra
        entra >> conditional
        frontdoor >> apim
        apim >> appgw
        appgw >> planner

        # Planner dispatches agents via Service Bus
        planner >> Edge(label="dispatch", style="dashed") >> servicebus
        servicebus >> code_agent
        servicebus >> research_agent
        servicebus >> data_agent
        servicebus >> devops_agent
        servicebus >> cicd_agent

        # All agents report back
        code_agent >> Edge(label="result") >> eventgrid
        research_agent >> eventgrid
        data_agent >> eventgrid
        qa_agent >> eventgrid
        devops_agent >> eventgrid
        eventgrid >> planner

        # QA validates all outputs
        planner >> Edge(label="validate") >> qa_agent

        # AI layer
        planner >> foundry
        code_agent >> foundry
        research_agent >> foundry
        foundry >> content_safety

        # Data
        planner >> cosmos
        code_agent >> cosmos
        data_agent >> cosmos
        planner >> redis

        # RAG
        research_agent >> ai_search

        # Workflow orchestration
        planner >> durable

        # Security
        planner >> keyvault
        appinsights >> loganalytics
        loganalytics >> sentinel


def identity_and_auth_flow():
    """Entra ID (Azure AD) + Microsoft Graph authentication flow."""
    with Diagram(
        "Production Auth - Entra ID + Microsoft Graph",
        filename=os.path.join(OUTPUT_DIR, "prod_auth_flow"),
        show=False,
        direction="LR",
        graph_attr={**GRAPH_ATTR, "dpi": "150"},
        edge_attr=EDGE_ATTR,
        node_attr=NODE_ATTR,
    ):
        user = Users("User / Service Principal")

        with Cluster("Microsoft Entra ID", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#06b6d4"}):
            entra = ActiveDirectory("Entra ID\n(Tenant)")
            conditional = ConditionalAccess("Conditional Access\n(MFA + Device)")
            managed_id = EntraManagedIdentities("Managed Identities\n(Passwordless)")
            app_reg = AzureUsers("App Registration\n(OAuth2 Client)")

        with Cluster("Authorization", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#f59e0b"}):
            apim = APIManagement("API Management\n(JWT Validation)")
            rbac = KeyVaults("RBAC Policies\n(Scoped Roles)")

        with Cluster("Agent Services", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#10b981"}):
            backend = ContainerApps("Backend API")
            agents = ContainerApps("Agent Fleet\n(Managed Identity)")

        with Cluster("Secrets & Tokens", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#f43f5e"}):
            keyvault = KeyVaults("Key Vault\n(Rotation Policy)")
            tokens = Storage("Token Cache\n(Redis)")

        # Flow
        user >> Edge(label="1. Login (OIDC)") >> entra
        entra >> Edge(label="2. MFA Challenge") >> conditional
        conditional >> Edge(label="3. JWT + Refresh") >> app_reg
        app_reg >> Edge(label="4. Bearer Token") >> apim
        apim >> Edge(label="5. Validated") >> backend
        backend >> Edge(label="6. On-behalf-of") >> agents
        agents >> Edge(label="Managed Identity\n(no secrets)") >> managed_id
        managed_id >> keyvault
        backend >> tokens
        apim >> rbac


def network_security_topology():
    """Zero-trust network with private endpoints and VNet isolation."""
    with Diagram(
        "Production Network - Zero Trust Topology",
        filename=os.path.join(OUTPUT_DIR, "prod_network_security"),
        show=False,
        direction="TB",
        graph_attr={**GRAPH_ATTR, "dpi": "150"},
        edge_attr=EDGE_ATTR,
        node_attr=NODE_ATTR,
    ):
        internet = Users("Internet Traffic")

        with Cluster("DMZ / Edge", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#f43f5e"}):
            waf = Firewall("Azure WAF\n(OWASP Rules)")
            frontdoor = FrontDoors("Front Door\n(DDoS Protection)")
            ddos = Firewall("DDoS Protection\nStandard")

        with Cluster("Hub VNet (10.0.0.0/16)", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#06b6d4"}):
            fw = Firewall("Azure Firewall\n(Egress Control)")
            bastion = VirtualNetworks("Azure Bastion\n(Admin Access)")

        with Cluster("Spoke VNet - App (10.1.0.0/16)", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#10b981"}):
            with Cluster("Subnet: agents (10.1.1.0/24)"):
                agents = ContainerApps("Agent Fleet\n(No Public IP)")
            with Cluster("Subnet: data (10.1.2.0/24)"):
                pe_cosmos = PrivateEndpoint("Private Endpoint\n→ Cosmos DB")
                pe_kv = PrivateEndpoint("Private Endpoint\n→ Key Vault")
                pe_ai = PrivateEndpoint("Private Endpoint\n→ AI Foundry")

        with Cluster("PaaS (Private Link)", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#8b5cf6"}):
            cosmos = CosmosDb("Cosmos DB\n(No Public Access)")
            keyvault = KeyVaults("Key Vault")
            foundry = AzureOpenAI("AI Foundry")

        # Flow
        internet >> frontdoor
        frontdoor >> waf
        waf >> ddos
        ddos >> fw
        fw >> agents
        agents >> pe_cosmos >> cosmos
        agents >> pe_kv >> keyvault
        agents >> pe_ai >> foundry
        fw >> bastion


def cicd_agent_pipeline():
    """CI/CD pipeline with autonomous agents and HITL gates."""
    with Diagram(
        "Production CI/CD - Agent-Enhanced Pipeline",
        filename=os.path.join(OUTPUT_DIR, "prod_cicd_pipeline"),
        show=False,
        direction="LR",
        graph_attr={**GRAPH_ATTR, "dpi": "150"},
        edge_attr=EDGE_ATTR,
        node_attr=NODE_ATTR,
    ):
        dev = Users("Developer")

        with Cluster("Source Control", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#06b6d4"}):
            github = Docker("GitHub\n(Push/PR)")

        with Cluster("CI/CD Agent Orchestration", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#f59e0b"}):
            cicd = ContainerApps("CI/CD Agent\n(Event-Driven)")
            code_review = ContainerApps("Code Agent\n(Auto Review)")
            qa_gen = ContainerApps("QA Agent\n(Test Gen)")
            security = MicrosoftDefenderForCloud("Security Scan\n(SAST/DAST)")

        with Cluster("HITL Gate", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#f43f5e"}):
            approval = LogicApps("Logic App\n(Teams Approval)")
            hitl = Users("Human Reviewer\n(Approve/Reject)")

        with Cluster("Deploy (Progressive)", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#10b981"}):
            acr = ACR("Container Registry")
            canary = ContainerApps("Canary (1%)")
            staging = ContainerApps("Staging (10%)")
            prod = ContainerApps("Production (100%)")
            monitor = ApplicationInsights("Health Monitor\n(Auto-Rollback)")

        # Flow
        dev >> Edge(label="git push") >> github
        github >> Edge(label="webhook") >> cicd
        cicd >> code_review
        cicd >> qa_gen
        cicd >> security
        code_review >> Edge(label="approved") >> approval
        qa_gen >> approval
        security >> approval
        approval >> hitl
        hitl >> Edge(label="approved") >> acr
        acr >> canary
        canary >> Edge(label="healthy 15m") >> staging
        staging >> Edge(label="healthy 30m") >> prod
        canary >> monitor
        staging >> monitor
        prod >> monitor


def observability_stack():
    """Full observability stack with agent-level metrics."""
    with Diagram(
        "Production Observability - Agent Telemetry",
        filename=os.path.join(OUTPUT_DIR, "prod_observability"),
        show=False,
        direction="TB",
        graph_attr={**GRAPH_ATTR, "dpi": "150"},
        edge_attr=EDGE_ATTR,
        node_attr=NODE_ATTR,
    ):
        with Cluster("Agent Fleet (Instrumented)", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#10b981"}):
            planner = ContainerApps("Planner")
            code_a = ContainerApps("Code Agent")
            qa_a = ContainerApps("QA Agent")
            devops_a = ContainerApps("DevOps Agent")

        with Cluster("Collection Layer", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#06b6d4"}):
            otel = FunctionApps("OpenTelemetry\nCollector")
            appinsights = ApplicationInsights("Application\nInsights")

        with Cluster("Analysis & Storage", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#f59e0b"}):
            loganalytics = LogAnalyticsWorkspaces("Log Analytics\n(KQL Queries)")
            cosmos = CosmosDb("Event Store\n(Immutable Audit)")

        with Cluster("Alerting & Response", graph_attr={"bgcolor": "#1e293b", "fontcolor": "#f43f5e"}):
            sentinel = Sentinel("Microsoft Sentinel\n(Threat Detection)")
            logic = LogicApps("Logic Apps\n(Alert → Teams/PagerDuty)")
            defender = MicrosoftDefenderForCloud("Defender\n(Runtime Protection)")

        # Agents emit telemetry
        planner >> otel
        code_a >> otel
        qa_a >> otel
        devops_a >> otel

        otel >> appinsights
        appinsights >> loganalytics
        appinsights >> cosmos

        loganalytics >> sentinel
        sentinel >> logic
        loganalytics >> defender


if __name__ == "__main__":
    print("Generating production system architecture...")
    production_system_architecture()
    print("Generating identity & auth flow...")
    identity_and_auth_flow()
    print("Generating network security topology...")
    network_security_topology()
    print("Generating CI/CD agent pipeline...")
    cicd_agent_pipeline()
    print("Generating observability stack...")
    observability_stack()
    print(f"Done! Production diagrams saved to {OUTPUT_DIR}/")
