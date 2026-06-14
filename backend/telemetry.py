"""
Telemetry Module — Azure Application Insights integration.

Auto-instruments FastAPI with OpenTelemetry when APPLICATIONINSIGHTS_CONNECTION_STRING
is set. No-op locally when the env var is absent.
"""

import logging
import os

logger = logging.getLogger(__name__)


def setup_telemetry():
    """Initialize Azure Monitor OpenTelemetry if connection string is configured."""
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")

    if not connection_string:
        logger.info("Telemetry disabled (APPLICATIONINSIGHTS_CONNECTION_STRING not set)")
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=connection_string,
            enable_live_metrics=True,
        )
        logger.info("Azure Application Insights telemetry initialized")
    except ImportError:
        logger.warning("azure-monitor-opentelemetry not installed — telemetry disabled")
    except Exception as exc:
        logger.warning("Failed to initialize telemetry: %s", exc)
