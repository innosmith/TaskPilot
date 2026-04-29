"""Minimale Test-Fixtures für TaskPilot Backend Tests."""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "email-graph"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "mcp-email"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
