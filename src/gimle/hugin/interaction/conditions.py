"""Condition class and built-in condition functions for Waiting interactions."""

from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    cast,
)

from gimle.hugin.utils.registry import Registry

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@dataclass
class Condition:
    """A condition is a function that evalutes the current state of the stack and returns a boolean.

    Attributes:
        registry: The registry of conditions.
        evaluator: The evaluator function to use.
        parameters: The parameters to pass to the evaluator.
    """

    registry: ClassVar[Registry["Callable"]] = Registry()

    evaluator: str
    parameters: Optional[Dict[str, Any]] = None

    @classmethod
    def register(
        cls,
    ) -> Callable[[Callable], Callable]:
        """Register a function as a condition with metadata (decorator style).

        This is the original decorator-based registration method, kept for backward compatibility.

        Args:
            func: The function to register as a condition.

        Returns:
            The registered function.
        """

        def decorator(func: Callable) -> Callable:
            cls.registry.register(func, name=func.__name__)
            return func

        return decorator

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        """Deserialize from dictionary.

        Args:
            data: The data to deserialize the condition from.

        Returns:
            The deserialized condition.
        """
        return cls(evaluator=data["evaluator"], parameters=data["parameters"])

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            The serialized condition.
        """
        return {
            "evaluator": self.evaluator,
            "parameters": self.parameters,
        }

    def evaluate(self, stack: "Stack", branch: Optional[str]) -> bool:
        """Evaluate the condition.

        Args:
            stack: The stack to evaluate the condition on.
            branch: The branch to evaluate the condition on.

        Returns:
            The result of the condition evaluation.
        """
        evaluator = self.registry.get(self.evaluator)
        if evaluator is None:
            raise ValueError(f"Evaluator {self.evaluator} not found")
        if self.parameters is None:
            return cast(bool, evaluator(stack, branch))
        return cast(
            bool, evaluator(stack=stack, branch=branch, **self.parameters)
        )


@Condition.register()
def all_branches_complete(
    branches: List[str], stack: "Stack", branch: Optional[str]
) -> bool:
    """Check if all branches are complete.

    Args:
        branches: The branches to check.
        stack: The stack to evaluate the condition on.
        branch: The branch to evaluate the condition on.

    Returns:
        True if still waiting (some branches incomplete).
        False if done waiting (all branches complete).

    This follows the Waiting convention where:
    - True = keep waiting (condition not satisfied)
    - False = done waiting (condition satisfied, proceed)
    """
    for b in branches:
        if not stack.is_branch_complete(b):
            # Some branch is not complete - still waiting
            return True
    # All branches complete - done waiting
    return False
