"""Agent task module."""

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from typing_extensions import NotRequired, TypedDict


class TaskParameter(TypedDict):
    """A typed dictionary representing a task parameter schema."""

    type: str
    description: str
    required: NotRequired[bool]
    default: NotRequired[Any]
    choices: NotRequired[List[str]]
    value: NotRequired[Any]


@dataclass
class Task:
    """A task definition.

    Attributes:
        name: Unique identifier for this task.
        description: Human-readable description of the task.
        parameters: Template parameters for the prompt.
        prompt: The prompt template (Jinja2).
        tools: Optional list of tool names for this task.
        system_template: Optional system prompt template name.
        llm_model: Optional LLM model override.
        next_task: Name of task to chain to after completion.
        task_sequence: Ordered list of tasks to execute in sequence.
        pass_result_as: Parameter name to inject previous task's result.
        chain_config: Config name to use for chained tasks.
    """

    name: str
    description: str
    prompt: str
    parameters: Dict[str, TaskParameter] = field(default_factory=dict)
    tools: Optional[List[str]] = None
    system_template: Optional[str] = None
    llm_model: Optional[str] = None
    # Task chaining
    next_task: Optional[str] = None
    task_sequence: Optional[List[str]] = None
    pass_result_as: Optional[str] = None
    chain_config: Optional[str] = None

    def __post_init__(self) -> None:
        """Initialize parameter values from defaults.

        This keeps the schema stable (type/description/etc.) while ensuring every
        parameter has a `value` field for template rendering (param.value).

        Note: We intentionally do NOT raise for missing required params here;
        that remains a runtime concern enforced via set_input_parameters(...).
        """
        self._validate_parameter_schemas()
        for _, spec in self.parameters.items():
            if "value" in spec:
                continue
            if "default" in spec:
                spec["value"] = spec.get("default")
            else:
                spec["value"] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the task to a dictionary.

        Returns:
            The dictionary representation of the task.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Deserialize the task from a dictionary.

        Args:
            data: The dictionary to deserialize the task from.

        Returns:
            The deserialized task.
        """
        return cls(**data)

    @staticmethod
    def _get_categorical_choices(name: str, spec: TaskParameter) -> List[str]:
        """Return categorical choices from a schema, supporting legacy aliases.

        We support `choices` as the canonical key, and also accept `categories` and
        `values` for backward compatibility with older task schemas.

        Args:
            name: The name of the parameter.
            spec: The parameter schema.

        Returns:
            The categorical choices.
        """
        choices = (
            spec.get("choices") or spec.get("categories") or spec.get("values")
        )
        if not isinstance(choices, list) or not all(
            isinstance(c, str) for c in choices
        ):
            raise ValueError(
                f"Categorical task parameter '{name}' must define "
                "a string list under 'choices'."
            )
        return choices

    def _validate_parameter_schemas(self) -> None:
        """Validate that parameters are strict schema objects (no legacy scalars).

        Args:
            self: The task to validate.
        """
        if not isinstance(self.parameters, dict):
            raise ValueError(
                "Task.parameters must be a dict of parameter schemas, got "
                f"{type(self.parameters).__name__}"
            )

        for name, spec in self.parameters.items():
            if not isinstance(spec, dict):
                raise ValueError(
                    f"Task parameter '{name}' must be a schema dict "
                    "(e.g. {type, description, required, default}), "
                    f"got {type(spec).__name__}. Old scalar-style parameters "
                    "are no longer supported."
                )
            if "type" not in spec or "description" not in spec:
                raise ValueError(
                    f"Task parameter '{name}' schema must include 'type' and "
                    "'description'."
                )
            if not isinstance(spec.get("type"), str):
                raise ValueError(
                    f"Task parameter '{name}'.type must be a string."
                )
            if not isinstance(spec.get("description"), str):
                raise ValueError(
                    f"Task parameter '{name}'.description must be a string."
                )
            if "required" in spec and not isinstance(spec["required"], bool):
                raise ValueError(
                    f"Task parameter '{name}'.required must be a boolean."
                )
            if spec.get("type") == "categorical":
                Task._get_categorical_choices(name, spec)

    def clone(self) -> "Task":
        """Clone the task.

        Returns:
            The cloned task.
        """
        return Task(
            name=self.name,
            description=self.description,
            parameters=deepcopy(self.parameters),
            prompt=self.prompt,
            tools=deepcopy(self.tools),
            system_template=self.system_template,
            llm_model=self.llm_model,
            next_task=self.next_task,
            task_sequence=deepcopy(self.task_sequence),
            pass_result_as=self.pass_result_as,
            chain_config=self.chain_config,
        )

    def set_input_parameters(self, input_params: Dict[str, Any]) -> "Task":
        """Validate provided parameters against schema.

        Args:
            input_params: Parameters provided by user/CLI.

        Returns:
            Validated parameters with defaults applied.

        Raises:
            ValueError: If required parameters are missing.
        """
        missing_required: List[str] = []
        new_task = self.clone()

        # Check all schema parameters
        for param_name, param_spec in new_task.parameters.items():
            param_type = param_spec.get("type", "string")
            is_required = param_spec.get("required", False)
            has_default = (
                "default" in param_spec and param_spec["default"] is not None
            )
            has_value = (
                "value" in param_spec and param_spec.get("value") is not None
            )

            if param_name in input_params:
                parameter_value = input_params[param_name]
                if param_type == "integer":
                    param_spec["value"] = int(parameter_value)
                elif param_type == "number":
                    param_spec["value"] = float(parameter_value)
                elif param_type == "boolean":
                    if isinstance(parameter_value, bool):
                        param_spec["value"] = parameter_value
                    elif isinstance(parameter_value, (int, float)):
                        param_spec["value"] = bool(parameter_value)
                    else:
                        param_spec["value"] = str(
                            parameter_value
                        ).strip().lower() in ("true", "yes", "1", "y")
                elif param_type == "array":
                    if isinstance(parameter_value, list):
                        param_spec["value"] = parameter_value
                    elif isinstance(parameter_value, str):
                        parsed = json.loads(parameter_value)
                        if not isinstance(parsed, list):
                            raise ValueError(
                                f"Parameter '{param_name}' must be a JSON array."
                            )
                        param_spec["value"] = parsed
                    else:
                        raise ValueError(
                            f"Parameter '{param_name}' must be an array."
                        )
                elif param_type == "object":
                    if isinstance(parameter_value, dict):
                        param_spec["value"] = parameter_value
                    elif isinstance(parameter_value, str):
                        parsed = json.loads(parameter_value)
                        if not isinstance(parsed, dict):
                            raise ValueError(
                                f"Parameter '{param_name}' must be a JSON object."
                            )
                        param_spec["value"] = parsed
                    else:
                        raise ValueError(
                            f"Parameter '{param_name}' must be an object."
                        )
                elif param_type == "categorical":
                    choices = self._get_categorical_choices(
                        param_name, param_spec
                    )

                    selected: Optional[str]
                    if isinstance(parameter_value, int):
                        # Allow 1-based numeric selection
                        idx = parameter_value - 1
                        selected = (
                            choices[idx] if 0 <= idx < len(choices) else None
                        )
                    else:
                        selected = str(parameter_value)

                    if selected not in choices:
                        choices_str = ", ".join(choices)
                        raise ValueError(
                            f"Invalid value for '{param_name}': {selected!r}. "
                            f"Allowed: [{choices_str}]"
                        )
                    param_spec["value"] = selected
                else:
                    param_spec["value"] = str(parameter_value)
            elif has_value:
                # Preserve an existing value (allows calling set_input_parameters
                # multiple times without clobbering earlier inputs).
                continue
            elif has_default:
                if param_type == "categorical":
                    choices = new_task._get_categorical_choices(
                        param_name, param_spec
                    )
                    default_value = param_spec["default"]
                    if default_value not in choices:
                        choices_str = ", ".join(choices)
                        raise ValueError(
                            f"Default for '{param_name}' must be one of "
                            f"[{choices_str}], got {default_value!r}"
                        )
                elif param_type == "array":
                    if not isinstance(param_spec["default"], list):
                        raise ValueError(
                            f"Default for '{param_name}' must be a list."
                        )
                elif param_type == "object":
                    if not isinstance(param_spec["default"], dict):
                        raise ValueError(
                            f"Default for '{param_name}' must be an object."
                        )
                param_spec["value"] = param_spec["default"]
            elif is_required:
                param_desc = param_spec["description"]
                desc_part = f": {param_desc}" if param_desc else ""
                missing_required.append(
                    f"'{param_name}' ({param_type}){desc_part}"
                )
            else:
                # Optional param with no default and no provided value.
                # Keep schema intact, set explicit None.
                param_spec["value"] = None

        if missing_required:
            params_str = "\n  - ".join(missing_required)
            raise ValueError(
                f"Missing required parameter(s) for task '{new_task.name}':\n"
                f"  - {params_str}"
            )

        new_task._validate_parameter_schemas()

        return new_task
