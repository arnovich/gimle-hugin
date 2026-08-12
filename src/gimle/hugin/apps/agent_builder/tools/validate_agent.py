"""Static validation of a generated (or hand-written) Hugin agent.

Replaces "an LLM read a preview string and said it looked fine" with mechanical
checks. Everything here is *static*: files are parsed, never imported and never
executed, so validating an agent cannot run the code it is validating. The
opt-in import check that does execute code lives behind ``check_imports`` and is
documented as a correctness aid, not a security boundary.

Errors block a write; warnings do not. The split matters because a warning that
blocks would push the repair loop toward deleting the offending feature, and
because several legitimate Hugin patterns look suspicious to a static reader --
a task parameter can be created at runtime by an upstream task's
``pass_result_as``, and a system template is rendered against several different
input sets over an agent's lifetime.
"""

import ast
import re
import sys
from pathlib import Path
from functools import lru_cache
from typing import (
    AbstractSet,
    Any,
    Dict,
    FrozenSet,
    List,
    Optional,
    Set,
    Tuple,
)

import yaml

from gimle.hugin.apps.agent_builder.tools.agent_paths import (
    validate_generated_key,
)
from gimle.hugin.tools.tool import ToolResponse

# Mirrors the identifier-only heuristic a bare template reference must match,
# so prose system prompts are not mistaken for a broken reference.
BARE_REFERENCE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

# Names the renderer injects into every template namespace. Referencing one is
# legitimate even though no task declares it.
RENDERER_PROVIDED = frozenset(
    {"agent", "stack", "format_df_to_string", "learnings"}
)

# Auto-injected by the tool dispatcher when a tool declares them.
INJECTED_PARAMS = frozenset({"stack", "branch", "self"})

# Import name -> distribution name, for the cases where they differ. An
# unmapped third-party import is reported as observed, not as a pip install
# instruction, because the name came from an LLM and may not exist.
DISTRIBUTION_NAMES = {
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
}

Finding = Dict[str, str]


def _finding(file: str, check: str, message: str) -> Finding:
    """Build one report entry."""
    return {"file": file, "check": check, "message": message}


def collect_files(agent_path: str) -> Dict[str, str]:
    """Read an agent directory into the ``{relative_path: content}`` shape.

    The same shape the builder holds in ``env_vars["generated_files"]``, so an
    on-disk agent and an in-memory one go through identical checks.
    """
    root = Path(agent_path)
    files: Dict[str, str] = {}
    for folder in ("configs", "tasks", "templates", "tools"):
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix not in (".yaml", ".py") or path.name.startswith(
                "__"
            ):
                continue
            files[f"{folder}/{path.name}"] = path.read_text()
    return files


def _load_yaml(files: Dict[str, str], folder: str) -> Dict[str, Any]:
    """Parse every YAML document in ``folder``, keyed by its file key."""
    documents: Dict[str, Any] = {}
    for key, content in files.items():
        if not key.startswith(f"{folder}/") or not key.endswith(".yaml"):
            continue
        try:
            documents[key] = yaml.safe_load(content) or {}
        except yaml.YAMLError as error:
            documents[key] = {"__parse_error__": str(error)}
    return documents


def _implementation(document: Dict[str, Any]) -> Tuple[str, str]:
    """Split ``implementation_path`` into ``(module_file_stem, function)``.

    The path is ``some.dotted.module:function``; only the last dotted segment
    names the file inside ``tools/``. Several tool definitions routinely share
    one module -- ``examples/parallel_agents`` puts ``increment`` and
    ``get_count`` in ``counter_tools.py`` -- so the YAML stem is not the module
    name and must not be assumed to be.
    """
    path = document.get("implementation_path") or ""
    module, _, function = path.partition(":")
    return module.split(".")[-1], function


def _declared_parameters(document: Dict[str, Any]) -> Dict[str, Any]:
    """Return a tool's parameters, accepting both schema styles.

    Most definitions map name -> spec directly. Some (``apps/rap_machine``)
    use a JSON-Schema object with the real parameters under ``properties``.
    """
    parameters = document.get("parameters") or {}
    if not isinstance(parameters, dict):
        return {}
    if parameters.get("type") == "object" and isinstance(
        parameters.get("properties"), dict
    ):
        return dict(parameters["properties"])
    return dict(parameters)


def _check_structure(files: Dict[str, str]) -> List[Finding]:
    """An agent needs a config and a task, and resolvable tool modules."""
    findings = []
    if not any(k.startswith("configs/") for k in files):
        findings.append(
            _finding("configs/", "structure", "no config file found")
        )
    if not any(k.startswith("tasks/") for k in files):
        findings.append(_finding("tasks/", "structure", "no task file found"))

    # A .py with no .yaml is a shared helper module, which is a normal and
    # widely used pattern -- only a definition pointing at a missing module is
    # a real break.
    for key, document in _load_yaml(files, "tools").items():
        module, _ = _implementation(document)
        if not module:
            continue
        if f"tools/{module}.py" not in files:
            findings.append(
                _finding(
                    key,
                    "structure",
                    f"implementation_path names module '{module}' but "
                    f"tools/{module}.py does not exist",
                )
            )
    return findings


@lru_cache(maxsize=1)
def _builtin_tool_names() -> FrozenSet[str]:
    """Return the ``builtins.*`` tool names, read from the builtins source.

    Deliberately *not* read from ``Tool.registry``. That registry is a mutable
    process-global: it accumulates every loaded agent's tools, and test
    fixtures reset it. Reading it made the same agent validate differently
    depending on what else had run -- reporting a shipped agent's own tools as
    collisions in one order, and ``builtins.finish`` as unregistered in
    another.

    Parsing the decorators instead makes the answer depend only on the
    installed source, which is what "static validation" should mean.
    """
    builtins_dir = Path(__file__).resolve().parents[3] / "tools" / "builtins"
    names: Set[str] = set()
    if not builtins_dir.is_dir():  # pragma: no cover - unusual install layout
        from gimle.hugin.tools.tool import Tool

        return frozenset(
            n for n in Tool.registry.registered() if n.startswith("builtins.")
        )

    pattern = re.compile(r"""name\s*=\s*["'](builtins\.[A-Za-z0-9_]+)["']""")
    for path in builtins_dir.glob("*.py"):
        names |= set(pattern.findall(path.read_text()))
    return frozenset(names)


def _check_reserved_names(files: Dict[str, str]) -> List[Finding]:
    """A generated name must not silently replace something that exists.

    ``Registry.register`` overwrites without complaint on a process-global
    registry, and generated tool modules are imported by bare name, so a tool
    called ``finish`` or a module called ``json`` shadows the real one for the
    whole process.
    """
    findings = []
    builtins_registered = _builtin_tool_names()
    definitions = _load_yaml(files, "tools")

    for key, document in definitions.items():
        name = document.get("name")
        if not isinstance(name, str):
            continue
        if name in builtins_registered or name.startswith("builtins."):
            findings.append(
                _finding(
                    key,
                    "reserved-name",
                    f"tool name '{name}' takes a builtin's name and would "
                    "silently replace it process-wide",
                )
            )

    # Collisions between two *generated* agents cannot be seen from one
    # directory -- they depend on what else is loaded. That belongs at
    # registration time (Registry.register(replace=False), PR 1.5), not here,
    # where guessing would make the verdict order-dependent.

    for key in files:
        if not key.startswith("tools/") or not key.endswith(".py"):
            continue
        module = Path(key).stem
        if module in sys.stdlib_module_names:
            findings.append(
                _finding(
                    key,
                    "reserved-name",
                    f"module name '{module}' shadows a standard library "
                    "module for every agent in the process",
                )
            )
    return findings


def _template_names(files: Dict[str, str]) -> Set[str]:
    """Collect the names templates register themselves under."""
    names = set()
    for document in _load_yaml(files, "templates").values():
        name = document.get("name")
        if isinstance(name, str):
            names.add(name)
    return names


def _own_tool_names(files: Dict[str, str]) -> Set[str]:
    """Collect the tool names this agent defines."""
    names = set()
    for document in _load_yaml(files, "tools").values():
        name = document.get("name")
        if isinstance(name, str):
            names.add(name)
    return names


def _check_template_reference(
    key: str, field: str, value: Any, known: Set[str]
) -> Optional[Finding]:
    """Flag a bare identifier that no registered template answers to.

    Only fires on identifier-shaped values: prose and explicit Jinja are both
    legitimate inline prompts, not broken references.
    """
    if not isinstance(value, str) or not BARE_REFERENCE.match(value):
        return None
    if value in known:
        return None
    return _finding(
        key,
        "template-reference",
        f"{field} '{value}' looks like a template reference but no template "
        "registers that name",
    )


def _check_tool_reference(
    key: str,
    entry: Any,
    own: Set[str],
    builtins_registered: AbstractSet[str],
) -> Tuple[Optional[Finding], Optional[Finding]]:
    """Resolve one config/task tool entry. Returns ``(error, warning)``.

    Entries are ``name``, ``namespace.name`` or ``namespace.name:alias``.
    A namespaced reference outside ``builtins.`` may be provided by another app
    loaded into the same environment, so it can only be a warning.
    """
    if not isinstance(entry, str):
        return None, None
    name = entry.split(":")[0]

    if name.startswith("builtins."):
        if name not in builtins_registered:
            return (
                _finding(
                    key,
                    "tool-reference",
                    f"builtin tool '{name}' is not registered",
                ),
                None,
            )
        return None, None

    if "." in name:
        if name not in builtins_registered:
            return None, _finding(
                key,
                "tool-reference",
                f"tool '{name}' is namespaced to another agent and cannot be "
                "resolved from this directory alone",
            )
        return None, None

    if name not in own and name not in builtins_registered:
        return (
            _finding(
                key,
                "tool-reference",
                f"tool '{name}' is not defined in tools/ and is not a "
                "registered tool",
            ),
            None,
        )
    return None, None


def _check_references(
    files: Dict[str, str],
) -> Tuple[List[Finding], List[Finding]]:
    """Every template and tool a config or task names must resolve."""
    errors: List[Finding] = []
    warnings: List[Finding] = []
    templates = _template_names(files)
    own_tools = _own_tool_names(files)
    builtins_registered = _builtin_tool_names()

    for folder in ("configs", "tasks"):
        for key, document in _load_yaml(files, folder).items():
            if "__parse_error__" in document:
                errors.append(
                    _finding(
                        key, "yaml", f"invalid YAML: {document['__parse_error__']}"
                    )
                )
                continue
            finding = _check_template_reference(
                key, "system_template", document.get("system_template"), templates
            )
            if finding:
                errors.append(finding)
            for entry in document.get("tools") or []:
                error, warning = _check_tool_reference(
                    key, entry, own_tools, builtins_registered
                )
                if error:
                    errors.append(error)
                if warning:
                    warnings.append(warning)
    return errors, warnings


def _jinja_names(source: str) -> Tuple[Set[str], Set[str]]:
    """Return ``(all_loaded_names, names_read_via_.value)`` from a template."""
    from jinja2 import Environment as JinjaEnvironment
    from jinja2 import nodes

    try:
        parsed = JinjaEnvironment().parse(source)
    except Exception:  # noqa: BLE001 - a bad template is reported elsewhere
        return set(), set()

    loaded = {node.name for node in parsed.find_all(nodes.Name)}
    dotted = {
        node.node.name
        for node in parsed.find_all(nodes.Getattr)
        if isinstance(node.node, nodes.Name) and node.attr == "value"
    }
    return loaded, dotted


def _pass_result_names(files: Dict[str, str]) -> Set[str]:
    """Parameters that upstream tasks create at runtime via pass_result_as.

    ``TaskChain.step`` injects these into the successor even when it never
    declared them, so treating them as undeclared would be a false positive.
    """
    names = set()
    for document in _load_yaml(files, "tasks").values():
        value = document.get("pass_result_as")
        if isinstance(value, str):
            names.add(value)
    return names


def _check_jinja(files: Dict[str, str]) -> List[Finding]:
    """Warn about prompt variables nothing will supply.

    Warnings only. The renderer's namespace is wide and partly dynamic, so a
    static reader cannot be certain enough to block a write on this.
    """
    findings: List[Finding] = []
    allowed_extra = (
        RENDERER_PROVIDED | _template_names(files) | _pass_result_names(files)
    )

    for key, document in _load_yaml(files, "tasks").items():
        prompt = document.get("prompt")
        if not isinstance(prompt, str):
            continue
        declared = set((document.get("parameters") or {}).keys())
        loaded, dotted = _jinja_names(prompt)

        for name in sorted(loaded - declared - allowed_extra):
            findings.append(
                _finding(
                    key,
                    "prompt-variable",
                    f"prompt uses '{{{{ {name} }}}}' but no parameter, "
                    "template or upstream task supplies it",
                )
            )
        for name in sorted((loaded & declared) - dotted):
            findings.append(
                _finding(
                    key,
                    "prompt-variable",
                    f"parameter '{name}' is referenced without '.value', "
                    "which renders the parameter object rather than its value",
                )
            )
    return findings


def _function_named(tree: ast.Module, name: str) -> Optional[ast.FunctionDef]:
    """Find a module-level function definition by name."""
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node  # type: ignore[return-value]
    return None


def _signature_names(function: ast.FunctionDef) -> Set[str]:
    """Every parameter name a function accepts."""
    args = function.args
    names = {a.arg for a in args.args}
    names |= {a.arg for a in args.posonlyargs}
    names |= {a.arg for a in args.kwonlyargs}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _observed_imports(tree: ast.Module, local: Set[str]) -> Set[str]:
    """Top-level third-party module names imported anywhere in the file.

    ``local`` names modules that ship with the agent itself -- a sibling tool
    module, or a package next to the agent like ``apps/the_hugins/world``.
    Reporting one as a dependency would put a nonexistent distribution into the
    generated requirements.
    """
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return {
        module
        for module in modules
        if module not in sys.stdlib_module_names
        and module != "gimle"
        and module not in local
    }


def local_module_names(agent_path: str, files: Dict[str, str]) -> Set[str]:
    """Names importable from inside the agent rather than from PyPI.

    Sibling tool modules always count. When an on-disk path is available, so
    does anything importable sitting beside the agent directory, since the
    apps add their own root to ``sys.path`` before running.
    """
    names = {
        Path(key).stem
        for key in files
        if key.startswith("tools/") and key.endswith(".py")
    }
    root = Path(agent_path) if agent_path else None
    if root and root.is_dir():
        for child in root.iterdir():
            if child.is_dir() and (child / "__init__.py").exists():
                names.add(child.name)
            elif child.suffix == ".py":
                names.add(child.stem)
    return names


def _check_tool_contracts(
    files: Dict[str, str], local: Set[str]
) -> Tuple[List[Finding], List[Finding], Set[str]]:
    """Each tool module must define the function its YAML advertises."""
    errors: List[Finding] = []
    warnings: List[Finding] = []
    imports: Set[str] = set()
    definitions = _load_yaml(files, "tools")

    trees: Dict[str, ast.Module] = {}
    for key, content in sorted(files.items()):
        if not key.startswith("tools/") or not key.endswith(".py"):
            continue
        try:
            trees[key] = ast.parse(content, filename=key)
        except SyntaxError as error:
            errors.append(
                _finding(key, "syntax", f"line {error.lineno}: {error.msg}")
            )
            continue
        imports |= _observed_imports(trees[key], local)

    for key, document in sorted(definitions.items()):
        module, function_name = _implementation(document)
        tree = trees.get(f"tools/{module}.py")
        if tree is None or not function_name:
            # A missing or unparseable module is already reported by the
            # structure and syntax checks; do not report it twice.
            continue

        function = _function_named(tree, function_name)
        if function is None:
            errors.append(
                _finding(
                    key,
                    "tool-contract",
                    f"implementation_path names '{function_name}' but "
                    f"tools/{module}.py defines no such module-level function",
                )
            )
            continue

        accepted = _signature_names(function)
        declared = _declared_parameters(document)
        for parameter in declared:
            if parameter not in accepted:
                errors.append(
                    _finding(
                        key,
                        "tool-contract",
                        f"parameter '{parameter}' is declared but "
                        f"'{function_name}' does not accept it",
                    )
                )

        required = _required_names(function) - INJECTED_PARAMS
        for parameter in sorted(required - set(declared)):
            warnings.append(
                _finding(
                    key,
                    "tool-contract",
                    f"'{function_name}' requires '{parameter}' but it is not "
                    "declared, so the model cannot supply it",
                )
            )
    return errors, warnings, imports


def _required_names(function: ast.FunctionDef) -> Set[str]:
    """Parameters with no default, which a caller must therefore supply."""
    args = function.args
    positional = args.posonlyargs + args.args
    without_default = positional[: len(positional) - len(args.defaults)]
    required = {a.arg for a in without_default}
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        if default is None:
            required.add(arg.arg)
    return required


def validate_files(
    files: Dict[str, str], agent_path: str = ""
) -> Dict[str, Any]:
    """Run every static check over an agent's files and build the report."""
    errors: List[Finding] = []
    warnings: List[Finding] = []

    for message in _key_errors(files):
        errors.append(_finding(message["file"], "path", message["message"]))

    errors += _check_structure(files)
    errors += _check_reserved_names(files)

    reference_errors, reference_warnings = _check_references(files)
    errors += reference_errors
    warnings += reference_warnings

    warnings += _check_jinja(files)

    local = local_module_names(agent_path, files)
    contract_errors, contract_warnings, imports = _check_tool_contracts(
        files, local
    )
    errors += contract_errors
    warnings += contract_warnings

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "observed_imports": sorted(
            DISTRIBUTION_NAMES.get(name, name) for name in imports
        ),
        "summary": (
            f"{len(errors)} error(s), {len(warnings)} warning(s)"
        ),
    }


def _key_errors(files: Dict[str, str]) -> List[Finding]:
    """Reject file keys that would escape the output directory."""
    findings = []
    for key in files:
        message = validate_generated_key(key)
        if message:
            findings.append({"file": key, "message": message})
    return findings


def validate_agent(
    stack: "Any" = None,
    agent_path: Optional[str] = None,
    check_imports: bool = False,
) -> ToolResponse:
    """Validate a generated agent without executing any of its code.

    Args:
        stack: Agent stack (auto-injected)
        agent_path: Directory to validate. Omit to validate the files the
            builder has generated so far, before anything reaches disk.
        check_imports: Reserved for the opt-in import check. Importing
            generated code executes it, so this is off by default and is a
            correctness aid, never a security boundary.

    Returns:
        ToolResponse whose content is the validation report.
    """
    if agent_path:
        try:
            files = collect_files(agent_path)
        except OSError as error:
            return ToolResponse(
                is_error=True,
                content={"error": f"Could not read {agent_path}: {error}"},
            )
        if not files:
            return ToolResponse(
                is_error=True,
                content={"error": f"No agent files found in {agent_path}"},
            )
    else:
        files = (
            stack.agent.environment.env_vars.get("generated_files", {})
            if stack is not None
            else {}
        )
        if not files:
            return ToolResponse(
                is_error=True,
                content={"error": "No files have been generated yet"},
            )

    report = validate_files(files, agent_path or "")
    if check_imports:
        report["warnings"].append(
            _finding(
                "-",
                "import-check",
                "check_imports is not implemented yet; imports were not run",
            )
        )
    return ToolResponse(is_error=not report["ok"], content=report)
