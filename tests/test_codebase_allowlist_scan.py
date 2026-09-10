"""
AST Codebase Security & Isolation Scanner (Gate 4 Verification).
Performs static AST analysis on all Python source files in src/ to verify:
1. Deny-list: No imports from 'atmos payment system', 'server', or forbidden paths.
2. Deny-list: No reading of '.env' directly or accessing 'docs/specs'.
3. Allow-list: All external dependencies are in the approved stack.
4. Zero write statements to MySQL core payment tables.
"""
import ast
import os
from pathlib import Path
import pytest

SRC_DIR = Path(__file__).parent.parent / "src"

ALLOWED_TOP_LEVEL_MODULES = {
    # Standard library
    "os", "sys", "re", "time", "json", "csv", "socket", "logging",
    "threading", "statistics", "datetime", "decimal", "collections",
    "typing", "hashlib", "ipaddress", "sqlite3", "pathlib", "math",
    "enum", "uuid", "urllib", "dataclasses",
    # Third-party runtime approved stack
    "pydantic", "flask", "werkzeug", "pymysql", "typer", "tabulate", "httpx",
    # Internal project package
    "src"
}

FORBIDDEN_IMPORT_SUBSTRINGS = [
    "atmos",
    "server",
    "payment_service",
    "payment_transaction_service",
    "system_api"
]

FORBIDDEN_STRING_LITERALS = [
    ".env",
    "docs/specs",
    "docs\\specs",
    "atmos payment system"
]


def get_all_python_files(directory: Path):
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith(".py"):
                yield Path(root) / f


def test_no_forbidden_imports_via_ast():
    """Verify that src/ never imports from atmos or legacy server modules."""
    violations = []
    
    for py_file in get_all_python_files(SRC_DIR):
        with open(py_file, "r", encoding="utf-8") as f:
            source = f.read()
        
        tree = ast.parse(source, filename=str(py_file))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
                        if forbidden in alias.name.lower():
                            violations.append(f"{py_file.name}: forbidden import '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
                    if forbidden in mod_name.lower():
                        violations.append(f"{py_file.name}: forbidden from-import '{mod_name}'")

    assert not violations, f"AST Security Violations found:\n" + "\n".join(violations)


def test_dependency_allowlist_via_ast():
    """Verify that all external imports in src/ conform strictly to the allow-list."""
    violations = []
    
    for py_file in get_all_python_files(SRC_DIR):
        with open(py_file, "r", encoding="utf-8") as f:
            source = f.read()
        
        tree = ast.parse(source, filename=str(py_file))
        
        for node in ast.walk(tree):
            mod = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    mod = node.module.split(".")[0]
            
            if mod and mod not in ALLOWED_TOP_LEVEL_MODULES:
                violations.append(f"{py_file.name}: unapproved dependency '{mod}'")

    assert not violations, f"Unapproved dependencies found:\n" + "\n".join(violations)


def test_deny_list_string_literals_and_paths():
    """Verify that no src/ files hardcode access to .env, docs/specs, or forbidden paths."""
    violations = []
    
    for py_file in get_all_python_files(SRC_DIR):
        with open(py_file, "r", encoding="utf-8") as f:
            source = f.read()
        
        tree = ast.parse(source, filename=str(py_file))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val_lower = node.value.lower()
                for forbidden in FORBIDDEN_STRING_LITERALS:
                    # Allow .env.example mention in docstrings/comments if needed, but not direct open(".env")
                    if forbidden == ".env" and val_lower == ".env":
                        violations.append(f"{py_file.name}:{node.lineno}: references forbidden '{forbidden}'")
                    elif forbidden != ".env" and forbidden in val_lower:
                        violations.append(f"{py_file.name}:{node.lineno}: references forbidden '{forbidden}'")

    assert not violations, f"Forbidden string/path references found:\n" + "\n".join(violations)


def test_zero_destructive_sql_in_src():
    """Verify that no destructive or modifying SQL queries exist in src/ against payment_transaction."""
    forbidden_sql = [
        "DROP TABLE",
        "ALTER TABLE",
        "TRUNCATE TABLE",
        "UPDATE payment_transaction",
        "DELETE FROM payment_transaction",
        "INSERT INTO payment_transaction"
    ]
    
    violations = []
    for py_file in get_all_python_files(SRC_DIR):
        with open(py_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        for sql in forbidden_sql:
            if sql in content:
                violations.append(f"{py_file.name}: contains forbidden SQL statement '{sql}'")

    assert not violations, f"Forbidden SQL modifications found in src:\n" + "\n".join(violations)
