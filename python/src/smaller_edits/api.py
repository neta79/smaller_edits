from __future__ import annotations

from .context import InMemoryToolContext
from .edit_tool import build_edit_tool
from .models import Toolset
from .read_tool import build_read_tool


def create_toolset(context: InMemoryToolContext) -> Toolset:
    return Toolset(
        read=build_read_tool(context),
        edit=build_edit_tool(context),
    )
