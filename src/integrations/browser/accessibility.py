"""Accessibility tree extraction and formatting for browser automation."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AccessibilityNode:
    """Node in the accessibility tree."""

    ref_id: int
    role: str
    name: str
    value: Optional[str] = None
    focused: bool = False
    disabled: bool = False
    children: List["AccessibilityNode"] = field(default_factory=list)
    selector: Optional[str] = None  # CSS selector to find element


class AccessibilityTreeFormatter:
    """Format accessibility trees for LLM consumption."""

    # Interactive roles that agents typically interact with
    INTERACTIVE_ROLES: Set[str] = {
        "link",
        "button",
        "textbox",
        "searchbox",
        "combobox",
        "checkbox",
        "radio",
        "menuitem",
        "tab",
        "option",
        "switch",
        "slider",
        "spinbutton",
    }

    # Form-related roles
    FORM_ROLES: Set[str] = {
        "textbox",
        "searchbox",
        "combobox",
        "checkbox",
        "radio",
        "button",
        "switch",
        "slider",
        "spinbutton",
    }

    def format_tree(
        self,
        nodes: List[AccessibilityNode],
        mode: str = "interactive",
        max_depth: int = 10,
        max_nodes: int = 100,
    ) -> str:
        """
        Format accessibility tree as compact text.

        Args:
            nodes: List of accessibility nodes
            mode: Filtering mode - "full", "interactive", or "forms"
            max_depth: Maximum tree depth
            max_nodes: Maximum number of nodes to include

        Returns:
            Formatted tree text with [ref=N] annotations
        """
        filtered = self._filter_nodes(nodes, mode)
        lines = []
        node_count = [0]  # Use list for mutability in closure

        def format_node(node: AccessibilityNode, depth: int = 0):
            if node_count[0] >= max_nodes or depth > max_depth:
                return

            indent = "  " * depth
            parts = [node.role]

            if node.name:
                # Truncate long names
                name = node.name[:50] + "..." if len(node.name) > 50 else node.name
                parts.append(f'"{name}"')

            if node.value:
                # Truncate long values
                value = node.value[:30] + "..." if len(node.value) > 30 else node.value
                parts.append(f'value="{value}"')

            if node.disabled:
                parts.append("[disabled]")

            parts.append(f"[ref={node.ref_id}]")

            lines.append(f"{indent}{' '.join(parts)}")
            node_count[0] += 1

            for child in node.children:
                format_node(child, depth + 1)

        for node in filtered:
            format_node(node)

        return "\n".join(lines) if lines else "(No elements found)"

    def _filter_nodes(self, nodes: List[AccessibilityNode], mode: str) -> List[AccessibilityNode]:
        """Filter nodes based on mode."""
        if mode == "full":
            return nodes
        elif mode == "interactive":
            return self._filter_by_roles(nodes, self.INTERACTIVE_ROLES)
        elif mode == "forms":
            return self._filter_by_roles(nodes, self.FORM_ROLES)
        else:
            return nodes

    def _filter_by_roles(
        self, nodes: List[AccessibilityNode], roles: Set[str]
    ) -> List[AccessibilityNode]:
        """Recursively filter nodes by role set."""
        filtered = []
        for node in nodes:
            if node.role in roles:
                # Include this node with filtered children
                filtered_children = self._filter_by_roles(node.children, roles)
                filtered_node = AccessibilityNode(
                    ref_id=node.ref_id,
                    role=node.role,
                    name=node.name,
                    value=node.value,
                    focused=node.focused,
                    disabled=node.disabled,
                    children=filtered_children,
                    selector=node.selector,
                )
                filtered.append(filtered_node)
            else:
                # Check children even if this node doesn't match
                filtered.extend(self._filter_by_roles(node.children, roles))
        return filtered

    def estimate_token_count(self, formatted: str) -> int:
        """Rough token count estimate (1 token ≈ 4 chars)."""
        return len(formatted) // 4


class AccessibilityTreeBuilder:
    """Build accessibility tree from Playwright snapshot."""

    def __init__(self):
        self.node_counter = 0
        self.ref_to_selector: Dict[int, str] = {}

    def build_tree(
        self, snapshot: Optional[Dict[str, Any]], include_invisible: bool = False
    ) -> List[AccessibilityNode]:
        """
        Build accessibility tree from Playwright snapshot.

        Args:
            snapshot: Playwright accessibility snapshot
            include_invisible: Include hidden/invisible elements

        Returns:
            List of root accessibility nodes
        """
        self.node_counter = 0
        self.ref_to_selector = {}

        if not snapshot:
            return []

        # Playwright returns a single root node or list
        if isinstance(snapshot, dict):
            node = self._build_node(snapshot, [], include_invisible)
            return [node] if node else []
        elif isinstance(snapshot, list):
            nodes = []
            for n in snapshot:
                node = self._build_node(n, [], include_invisible)
                if node:
                    nodes.append(node)
            return nodes
        else:
            return []

    def _build_node(
        self,
        node: Dict[str, Any],
        parent_path: List[str],
        include_invisible: bool,
    ) -> Optional[AccessibilityNode]:
        """Recursively build node tree."""
        # Skip invisible elements unless requested
        if not include_invisible:
            # Check various visibility properties
            if not node.get("visible", True):
                return None
            if node.get("hidden", False):
                return None

        role = node.get("role", "generic")
        name = node.get("name", "")

        # Skip purely structural roles with no name
        if role in {"generic", "none", "presentation"} and not name:
            # Still process children
            children = []
            for i, child in enumerate(node.get("children", [])):
                child_path = parent_path + [f"{role}[{i}]"]
                child_node = self._build_node(child, child_path, include_invisible)
                if child_node:
                    children.append(child_node)
            # Return children directly (flatten tree)
            return children[0] if len(children) == 1 else None

        # Assign unique ref ID
        ref_id = self.node_counter
        self.node_counter += 1

        # Build CSS selector hint
        selector = self._build_selector(node, role, name)
        self.ref_to_selector[ref_id] = selector

        # Build children
        children = []
        child_nodes = node.get("children", [])
        for i, child in enumerate(child_nodes):
            child_path = parent_path + [f"{role}[{i}]"]
            child_node = self._build_node(child, child_path, include_invisible)
            if child_node:
                children.append(child_node)

        return AccessibilityNode(
            ref_id=ref_id,
            role=role,
            name=name,
            value=node.get("value"),
            focused=node.get("focused", False),
            disabled=node.get("disabled", False),
            children=children,
            selector=selector,
        )

    def _build_selector(self, node: Dict[str, Any], role: str, name: str) -> str:
        """Build CSS selector for node (best effort)."""
        # Try to build a selector that Playwright can use

        # For links, use text content
        if role == "link" and name:
            # Escape quotes in name
            safe_name = name.replace("'", "\\'")[:30]
            return f"a:has-text('{safe_name}')"

        # For buttons
        if role == "button" and name:
            safe_name = name.replace("'", "\\'")[:30]
            return f"button:has-text('{safe_name}')"

        # For inputs with accessible names
        if role in {"textbox", "searchbox"} and name:
            safe_name = name.replace("'", "\\'")[:30]
            return f"input[aria-label*='{safe_name}']"

        # For elements with accessible names, try aria-label
        if name:
            safe_name = name.replace("'", "\\'")[:30]
            return f"[aria-label*='{safe_name}']"

        # Generic fallback to role
        return f"[role='{role}']"

    def get_selector_for_ref(self, ref_id: int) -> Optional[str]:
        """Get CSS selector for a reference ID."""
        return self.ref_to_selector.get(ref_id)
