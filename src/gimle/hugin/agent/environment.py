"""Agent environment module."""

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Optional, Set

import yaml

from gimle.hugin.agent.config import Config
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.query_engine import ArtifactQueryEngine
from gimle.hugin.llm.prompt.template import Template
from gimle.hugin.tools.tool import Tool
from gimle.hugin.utils.registry import Registry

if TYPE_CHECKING:
    from gimle.hugin.storage.storage import Storage

logger = logging.getLogger(__name__)


class Environment:
    """An environment is a collection of configurations and their registries."""

    # Track loaded extension paths to avoid duplicate imports
    _loaded_extensions: ClassVar[Set[str]] = set()

    # Builtin agents registry (shared across all environments)
    _builtin_configs: ClassVar[Dict[str, Config]] = {}
    _builtin_tasks: ClassVar[Dict[str, Task]] = {}
    _builtin_templates: ClassVar[Dict[str, "Template"]] = {}
    _builtins_loaded: ClassVar[bool] = False

    def __init__(
        self,
        storage: Optional["Storage"] = None,
        env_vars: Optional[Dict[str, Any]] = None,
        package_path: Optional[str] = None,
    ) -> None:
        """Initialize an environment with empty registries.

        Args:
            storage: Optional storage instance
            env_vars: Optional dictionary of environment variables accessible to tools
            package_path: Optional path to the package directory this env was loaded from
        """
        self.config_registry: Registry[Config] = Registry()
        self.task_registry: Registry[Task] = Registry()
        self.template_registry: Registry[Template] = Registry()
        self.storage = storage
        self.env_vars: Dict[str, Any] = env_vars or {}
        self._query_engine: Optional[ArtifactQueryEngine] = None
        self.package_path: Optional[str] = package_path

    @property
    def tool_registry(self) -> Registry[Tool]:
        """Get the tool registry.

        Returns:
            The tool registry.
        """
        return Tool.registry

    @property
    def query_engine(self) -> ArtifactQueryEngine:
        """Get the artifact query engine, creating it lazily if needed.

        Returns:
            The artifact query engine.
        """
        if self._query_engine is None:
            if self.storage is None:
                raise ValueError(
                    "Cannot create query engine without storage. "
                    "Please initialize Environment with a storage instance."
                )
            self._query_engine = ArtifactQueryEngine(self.storage)
        return self._query_engine

    @staticmethod
    def _load_extensions(package_path: str) -> None:
        """Load custom artifact types and UI components from package directory.

        Looks for:
        - artifact_types/ - Custom Artifact subclasses with @Artifact.register()
        - ui_components/ - Custom ArtifactComponent subclasses with
          @ComponentRegistry.register()

        Args:
            package_path: Path to the package directory
        """
        path_obj = Path(package_path)
        if not path_obj.is_absolute():
            path_obj = path_obj.resolve()
        path_str = str(path_obj)

        # Avoid loading the same extensions twice
        if path_str in Environment._loaded_extensions:
            return
        Environment._loaded_extensions.add(path_str)

        # Add parent to sys.path for imports (e.g., examples/ for custom_artifacts)
        parent_str = str(path_obj.parent)
        if parent_str not in sys.path:
            sys.path.insert(0, parent_str)

        package_name = path_obj.name

        for subdir in ["artifact_types", "ui_components"]:
            ext_dir = path_obj / subdir
            if not ext_dir.exists():
                continue

            init_file = ext_dir / "__init__.py"
            if init_file.exists():
                # Import the package to trigger decorator registration
                module_name = f"{package_name}.{subdir}"
                try:
                    # First, ensure parent package exists in sys.modules
                    if package_name not in sys.modules:
                        # Create a simple namespace for the parent package
                        import types

                        parent_pkg = types.ModuleType(package_name)
                        parent_pkg.__path__ = [str(path_obj)]
                        parent_pkg.__package__ = package_name
                        sys.modules[package_name] = parent_pkg

                    spec = importlib.util.spec_from_file_location(
                        module_name,
                        init_file,
                        submodule_search_locations=[str(ext_dir)],
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        module.__package__ = module_name
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                        logger.debug(f"Loaded extension module: {module_name}")
                except Exception as e:
                    logger.warning(
                        f"Failed to load extension {module_name}: {e}"
                    )
            else:
                # No __init__.py, try importing individual .py files
                for py_file in ext_dir.glob("*.py"):
                    if py_file.name.startswith("_"):
                        continue
                    module_name = f"{package_name}.{subdir}.{py_file.stem}"
                    try:
                        spec = importlib.util.spec_from_file_location(
                            module_name, py_file
                        )
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            sys.modules[module_name] = module
                            spec.loader.exec_module(module)
                            logger.debug(
                                f"Loaded extension module: {module_name}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to load extension {module_name}: {e}"
                        )

    @staticmethod
    def load(
        package_path: str,
        storage: Optional["Storage"] = None,
        env_vars: Optional[Dict[str, Any]] = None,
    ) -> "Environment":
        """Load the environment from a path.

        Args:
            package_path: Path to the package directory
            storage: Optional storage instance
            env_vars: Optional dictionary of environment variables accessible to tools

        Returns:
            The environment.
        """
        # Add project root to Python path to enable importing example modules
        # The package_path is something like "examples/data_analyst" or "/path/to/examples/data_analyst"
        package_path_obj = Path(package_path)
        if not package_path_obj.is_absolute():
            # Resolve relative paths to absolute
            package_path_obj = package_path_obj.resolve()

        # Create environment with the resolved package path
        env = Environment(
            storage=storage,
            env_vars=env_vars,
            package_path=str(package_path_obj),
        )

        project_root = package_path_obj.parent

        # Add to sys.path if not already there
        project_root_str = str(project_root)
        if project_root_str not in sys.path:
            sys.path.insert(0, project_root_str)

        config_folder = os.path.join(package_path, "configs")
        if os.path.exists(config_folder):
            for config_file in os.listdir(config_folder):
                if not config_file.endswith(".yaml"):
                    continue
                yaml_path = os.path.join(config_folder, config_file)
                with open(yaml_path, "r") as file:
                    config_yaml = yaml.safe_load(file)
                config = Config.from_dict(config_yaml)
                env.config_registry.register(config)

        task_folder = os.path.join(package_path, "tasks")
        if os.path.exists(task_folder):
            for task_file in os.listdir(task_folder):
                if not task_file.endswith(".yaml"):
                    continue
                yaml_path = os.path.join(task_folder, task_file)
                with open(yaml_path, "r") as file:
                    task_yaml = yaml.safe_load(file)
                task = Task.from_dict(task_yaml)
                env.task_registry.register(task)

        tool_folder = os.path.join(package_path, "tools")
        if os.path.exists(tool_folder):
            sys.path.append(tool_folder)
            for tool_file in os.listdir(tool_folder):
                if not tool_file.endswith(".yaml"):
                    continue
                yaml_path = os.path.join(tool_folder, tool_file)
                with open(yaml_path, "r") as file:
                    tool_yaml = yaml.safe_load(file)
                tool = Tool.from_dict(tool_yaml)
                # register_instance will load the implementation if implementation_path is provided
                Tool.register_instance(tool)

        template_folder = os.path.join(package_path, "templates")
        if os.path.exists(template_folder):
            for template_file in os.listdir(template_folder):
                if not template_file.endswith(".yaml"):
                    continue
                yaml_path = os.path.join(template_folder, template_file)
                with open(yaml_path, "r") as file:
                    template_yaml = yaml.safe_load(file)
                template = Template.from_dict(template_yaml)
                env.template_registry.register(template)

        # Load custom artifact types and UI components if present
        Environment._load_extensions(str(package_path_obj))

        # Load builtin agents
        Environment._load_builtin_agents()

        return env

    @classmethod
    def _load_builtin_agents(cls) -> None:
        """Load builtin agents from the apps directory.

        Builtin agents (like agent_builder) are always available.
        They are loaded once and shared across all environments.
        """
        if cls._builtins_loaded:
            return

        try:
            from gimle.hugin.apps import get_apps_path

            apps_path = get_apps_path()

            # Load agent_builder as a builtin agent
            agent_builder_path = apps_path / "agent_builder"
            if agent_builder_path.exists():
                cls._load_builtin_agent_from_path(
                    str(agent_builder_path), "builtins.agent_builder"
                )

            cls._builtins_loaded = True
            logger.debug("Loaded builtin agents")

        except Exception as e:
            logger.warning(f"Failed to load builtin agents: {e}")

    @classmethod
    def _load_builtin_agent_from_path(
        cls, package_path: str, prefix: str
    ) -> None:
        """Load a builtin agent from a path with a given prefix.

        Args:
            package_path: Path to the agent directory
            prefix: Prefix for the agent name (e.g., "builtins.agent_builder")
        """
        package_path_obj = Path(package_path)

        # Add to sys.path for tool imports
        if str(package_path_obj) not in sys.path:
            sys.path.insert(0, str(package_path_obj))
        if str(package_path_obj.parent) not in sys.path:
            sys.path.insert(0, str(package_path_obj.parent))

        # Load configs
        config_folder = package_path_obj / "configs"
        if config_folder.exists():
            for config_file in config_folder.iterdir():
                if not config_file.suffix == ".yaml":
                    continue
                with open(config_file, "r") as f:
                    config_yaml = yaml.safe_load(f)
                config = Config.from_dict(config_yaml)
                # Main config (matching the folder name) gets just the prefix
                # Other configs get prefix.config_name
                folder_name = package_path_obj.name
                if config.name == folder_name:
                    builtin_name = prefix
                else:
                    builtin_name = f"{prefix}.{config.name}"
                cls._builtin_configs[builtin_name] = config
                logger.debug(f"Loaded builtin config: {builtin_name}")

        # Load tasks
        task_folder = package_path_obj / "tasks"
        if task_folder.exists():
            for task_file in task_folder.iterdir():
                if not task_file.suffix == ".yaml":
                    continue
                with open(task_file, "r") as f:
                    task_yaml = yaml.safe_load(f)
                task = Task.from_dict(task_yaml)
                task_name = f"{prefix}.{task.name}"
                cls._builtin_tasks[task_name] = task
                logger.debug(f"Loaded builtin task: {task_name}")

        # Load tools
        tool_folder = package_path_obj / "tools"
        if tool_folder.exists():
            if str(tool_folder) not in sys.path:
                sys.path.insert(0, str(tool_folder))
            for tool_file in tool_folder.iterdir():
                if not tool_file.suffix == ".yaml":
                    continue
                with open(tool_file, "r") as f:
                    tool_yaml = yaml.safe_load(f)
                tool = Tool.from_dict(tool_yaml)
                Tool.register_instance(tool)

        # Load templates
        template_folder = package_path_obj / "templates"
        if template_folder.exists():
            for template_file in template_folder.iterdir():
                if not template_file.suffix == ".yaml":
                    continue
                with open(template_file, "r") as f:
                    template_yaml = yaml.safe_load(f)
                template = Template.from_dict(template_yaml)
                template_name = f"{prefix}.{template.name}"
                cls._builtin_templates[template_name] = template
                logger.debug(f"Loaded builtin template: {template_name}")

    def get_builtin_config(self, name: str) -> Optional[Config]:
        """Get a builtin agent config by name.

        Args:
            name: Config name (e.g., "builtins.agent_builder")

        Returns:
            The config if found, None otherwise.
        """
        Environment._load_builtin_agents()
        return Environment._builtin_configs.get(name)

    def get_builtin_task(self, name: str) -> Optional[Task]:
        """Get a builtin task by name.

        Args:
            name: Task name (e.g., "builtins.agent_builder.build_agent")

        Returns:
            The task if found, None otherwise.
        """
        Environment._load_builtin_agents()
        return Environment._builtin_tasks.get(name)

    def get_builtin_template(self, name: str) -> Optional[Template]:
        """Get a builtin template by name.

        Args:
            name: Template name

        Returns:
            The template if found, None otherwise.
        """
        Environment._load_builtin_agents()
        return Environment._builtin_templates.get(name)

    def get_all_configs(self) -> Dict[str, Config]:
        """Get all configs including builtins.

        Returns:
            Dictionary of all configs (environment + builtins).
        """
        Environment._load_builtin_agents()
        all_configs = dict(Environment._builtin_configs)
        all_configs.update(self.config_registry._items)
        return all_configs

    def load_agent_from_path(self, agent_path: str) -> Optional[str]:
        """Dynamically load an agent from a path into this environment.

        This is used to register newly created agents so they become
        available to list_agents and launch_agent.

        Args:
            agent_path: Path to the agent directory

        Returns:
            The name of the loaded agent config, or None if loading failed.
        """
        agent_path_obj = Path(agent_path)
        if not agent_path_obj.is_absolute():
            agent_path_obj = agent_path_obj.resolve()

        if not agent_path_obj.exists():
            logger.warning(f"Agent path does not exist: {agent_path}")
            return None

        # Add to sys.path for tool imports
        if str(agent_path_obj) not in sys.path:
            sys.path.insert(0, str(agent_path_obj))
        if str(agent_path_obj.parent) not in sys.path:
            sys.path.insert(0, str(agent_path_obj.parent))

        loaded_config_name = None

        try:
            # Load configs
            config_folder = agent_path_obj / "configs"
            if config_folder.exists():
                for config_file in config_folder.iterdir():
                    if not config_file.suffix == ".yaml":
                        continue
                    with open(config_file, "r") as f:
                        config_yaml = yaml.safe_load(f)
                    config = Config.from_dict(config_yaml)
                    self.config_registry.register(config)
                    loaded_config_name = config.name
                    logger.info(f"Loaded agent config: {config.name}")

            # Load tasks
            task_folder = agent_path_obj / "tasks"
            if task_folder.exists():
                for task_file in task_folder.iterdir():
                    if not task_file.suffix == ".yaml":
                        continue
                    with open(task_file, "r") as f:
                        task_yaml = yaml.safe_load(f)
                    task = Task.from_dict(task_yaml)
                    self.task_registry.register(task)
                    logger.debug(f"Loaded task: {task.name}")

            # Load tools
            tool_folder = agent_path_obj / "tools"
            if tool_folder.exists():
                if str(tool_folder) not in sys.path:
                    sys.path.insert(0, str(tool_folder))
                for tool_file in tool_folder.iterdir():
                    if not tool_file.suffix == ".yaml":
                        continue
                    with open(tool_file, "r") as f:
                        tool_yaml = yaml.safe_load(f)
                    tool = Tool.from_dict(tool_yaml)
                    Tool.register_instance(tool)
                    logger.debug(f"Loaded tool: {tool.name}")

            # Load templates
            template_folder = agent_path_obj / "templates"
            if template_folder.exists():
                for template_file in template_folder.iterdir():
                    if not template_file.suffix == ".yaml":
                        continue
                    with open(template_file, "r") as f:
                        template_yaml = yaml.safe_load(f)
                    template = Template.from_dict(template_yaml)
                    self.template_registry.register(template)
                    logger.debug(f"Loaded template: {template.name}")

            return loaded_config_name

        except Exception as e:
            logger.error(f"Failed to load agent from {agent_path}: {e}")
            return None
