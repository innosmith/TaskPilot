"""Geteilter Graph-Client-Factory.

Stellt einen einheitlich konfigurierten `GraphClient` (aus der Shared Library
`src/email-graph/graph_client.py`) bereit, damit Router (z. B. OneDrive, Chat)
und Hintergrund-Services (Hermes-Worker) denselben Client für den
`context_resolver` verwenden können.
"""

import logging
import os
import sys

from app.config import get_settings

logger = logging.getLogger(__name__)

_EMAIL_GRAPH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "email-graph"
)


def get_graph_client():
    """Erstellt einen GraphClient mit den konfigurierten Credentials.

    Returns:
        GraphClient oder None, wenn Graph nicht konfiguriert ist.
    """
    if _EMAIL_GRAPH_PATH not in sys.path:
        sys.path.insert(0, _EMAIL_GRAPH_PATH)
    from graph_client import GraphClient, GraphConfig  # noqa: E402

    s = get_settings()
    if not s.graph_tenant_id or not s.graph_client_id:
        return None

    config = GraphConfig(
        tenant_id=s.graph_tenant_id,
        client_id=s.graph_client_id,
        client_secret=s.graph_client_secret,
        user_email=s.graph_user_email,
    )
    return GraphClient(config)
