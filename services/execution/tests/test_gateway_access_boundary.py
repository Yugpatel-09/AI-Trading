import ast
import os
from pathlib import Path


def test_no_code_outside_order_manager_calls_place_order_or_imports_gateway_directly():
    """
    Architectural Static Verification Test (WP-B Requirement 2).
    Scans the entire codebase and fails if any code outside OrderManager calls
    `place_order` or imports a gateway directly.

    Enforces Non-Negotiable Rule 1: Every order must pass through OrderManager and Risk Guard.
    No code path may directly interface with a broker gateway.
    """
    repo_root = Path(__file__).resolve().parents[3]

    forbidden_import_modules = {
        "services.execution.gateway",
        "services.execution.gateway.base",
        "services.execution.gateway.paper_broker",
        "services.execution.gateway.zerodha_adapter",
    }
    forbidden_import_names = {
        "BrokerGateway",
        "PaperBroker",
        "ZerodhaAdapter",
    }

    # Whitelisted modules that are permitted to define/manage gateways
    whitelisted_subpaths = [
        os.path.join("services", "execution", "gateway"),
        os.path.join("services", "execution", "order_manager.py"),
        os.path.join("services", "execution", "order_manager"),
    ]

    violations = []

    # Directories to scan in the monorepo
    scan_dirs = [
        repo_root / "services",
        repo_root / "packages",
        repo_root / "apps",
    ]

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue

        for py_path in scan_dir.rglob("*.py"):
            str_path = str(py_path.resolve())

            # Skip unit test files and test directories
            if "/tests/" in str_path or py_path.name.startswith("test_") or "conftest.py" in py_path.name:
                continue

            # Skip whitelisted gateway implementations and OrderManager itself
            if any(allowed in str_path for allowed in whitelisted_subpaths):
                continue

            try:
                with open(py_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    tree = ast.parse(content, filename=str(py_path))
            except Exception as e:
                violations.append(f"Failed to parse {py_path}: {e}")
                continue

            for node in ast.walk(tree):
                # 1. Check for `import ...`
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_import_modules:
                            violations.append(
                                f"Direct gateway import violation in {py_path.relative_to(repo_root)}:{node.lineno} "
                                f"(`import {alias.name}`)"
                            )

                # 2. Check for `from ... import ...`
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if any(mod == f or mod.startswith(f + ".") for f in forbidden_import_modules):
                        violations.append(
                            f"Direct gateway import violation in {py_path.relative_to(repo_root)}:{node.lineno} "
                            f"(`from {mod} import ...`)"
                        )
                    for alias in node.names:
                        if alias.name in forbidden_import_names:
                            violations.append(
                                f"Direct gateway class import violation in {py_path.relative_to(repo_root)}:{node.lineno} "
                                f"(`from {mod} import {alias.name}`)"
                            )

                # 3. Check for method calls to `place_order`
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "place_order":
                        violations.append(
                            f"Unauthorized `place_order` invocation in {py_path.relative_to(repo_root)}:{node.lineno}. "
                            "Only OrderManager may invoke `place_order`."
                        )

    assert not violations, (
        f"Found {len(violations)} architectural boundary violations! "
        f"No code outside OrderManager may import gateways or call place_order:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
