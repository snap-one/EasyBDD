"""
Variable Loader for Environments, Collections, and Test Suites
Loads variables from JSON files and integrates with VariableManager
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .variable_manager import VariableManager


def load_environment_variables(
    variable_manager: VariableManager, project_root: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Load variables from the active environment file

    Args:
        variable_manager: VariableManager instance to load variables into
        project_root: Root directory of the project (defaults to current working directory)

    Returns:
        Dictionary of environment variables, or None if no active environment found
    """
    if project_root is None:
        project_root = Path.cwd()

    environments_dir = project_root / "environments"
    if not environments_dir.exists():
        return None

    # Find active environment
    active_env = None
    for env_file in environments_dir.glob("*.json"):
        try:
            with open(env_file, "r") as f:
                data = json.load(f)
                if data.get("is_active", False):
                    active_env = data
                    break
        except Exception:
            continue

    if not active_env:
        return None

    # Load variables into environment_vars scope
    env_scope = variable_manager.get_scope("environment_vars")
    if env_scope:
        env_scope.update(active_env.get("variables", {}))

    return active_env.get("variables", {})


def load_collection_variables(
    variable_manager: VariableManager,
    workspace_name: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load variables from a collection/workspace file

    Args:
        variable_manager: VariableManager instance to load variables into
        workspace_name: Name of the workspace/collection to load
        project_root: Root directory of the project (defaults to current working directory)

    Returns:
        Dictionary of collection variables, or None if not found
    """
    if project_root is None:
        project_root = Path.cwd()

    collections_dir = project_root / "collections"
    if not collections_dir.exists():
        return None

    if not workspace_name:
        return None

    # Find collection by name
    collection_data = None
    for collection_file in collections_dir.glob("*.json"):
        try:
            with open(collection_file, "r") as f:
                data = json.load(f)
                if data.get("name") == workspace_name:
                    collection_data = data
                    break
        except Exception:
            continue

    if not collection_data:
        return None

    # Load variables into collection_vars scope
    collection_scope = variable_manager.get_scope("collection_vars")
    if collection_scope:
        collection_scope.update(collection_data.get("variables", {}))

    return collection_data.get("variables", {})


def load_suite_variables(
    variable_manager: VariableManager,
    suite_id: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load variables from a test suite variables file

    Args:
        variable_manager: VariableManager instance to load variables into
        suite_id: ID of the test suite to load variables for
        project_root: Root directory of the project (defaults to current working directory)

    Returns:
        Dictionary of suite variables, or None if not found
    """
    if project_root is None:
        project_root = Path.cwd()

    if not suite_id:
        return None

    test_suites_dir = project_root / "test_suites"
    if not test_suites_dir.exists():
        return None

    # Load suite variables file
    variables_file = test_suites_dir / f"{suite_id}_variables.json"
    if not variables_file.exists():
        return None

    try:
        with open(variables_file, "r") as f:
            data = json.load(f)
            suite_vars = data.get("variables", {})

            # Load variables into suite_vars scope
            suite_scope = variable_manager.get_scope("suite_vars")
            if suite_scope:
                suite_scope.update(suite_vars)

            return suite_vars
    except Exception:
        return None


def load_all_variables(
    variable_manager: VariableManager,
    workspace_name: Optional[str] = None,
    suite_id: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load all variables from environments, collections, and suites

    Args:
        variable_manager: VariableManager instance to load variables into
        workspace_name: Name of the workspace/collection to load
        suite_id: ID of the test suite to load variables for
        project_root: Root directory of the project (defaults to current working directory)

    Returns:
        Dictionary containing all loaded variables by scope
    """
    result = {"environment": {}, "collection": {}, "suite": {}}

    # Load environment variables
    env_vars = load_environment_variables(variable_manager, project_root)
    if env_vars:
        result["environment"] = env_vars

    # Load collection variables
    if workspace_name:
        collection_vars = load_collection_variables(
            variable_manager, workspace_name, project_root
        )
        if collection_vars:
            result["collection"] = collection_vars

    # Load suite variables
    if suite_id:
        suite_vars = load_suite_variables(variable_manager, suite_id, project_root)
        if suite_vars:
            result["suite"] = suite_vars

    return result
