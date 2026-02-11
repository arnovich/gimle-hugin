"""Condition class and built-in condition functions for Waiting interactions."""

import logging
import time
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

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@dataclass
class Condition:
    """A condition that evaluates the current state of the stack.

    Condition evaluators are called on every step while the agent is
    waiting.  Most evaluators are pure (read-only), but some — like
    ``wait_for_ticks`` — mutate shared state as a side effect. Such
    evaluators must only be called once per step; calling them more
    than once (e.g. for logging or debugging) will advance their
    internal counters incorrectly.

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


@Condition.register()
def wait_for_ticks(stack: "Stack", branch: Optional[str], ticks: int) -> bool:
    """Wait for a specified number of ticks (session steps).

    Uses the last Waiting interaction's UUID as a unique key in shared
    state to track how many ticks have elapsed. Returns True (keep
    waiting) until the counter reaches ``ticks``, then returns False
    (done waiting) and cleans up the state key.

    .. note::

        This evaluator mutates shared state on every call. It must
        only be evaluated once per step.

    Args:
        stack: The stack to evaluate the condition on.
        branch: The branch to evaluate the condition on.
        ticks: Number of ticks to wait before proceeding (must be >= 1).

    Returns:
        True if still waiting (counter < ticks).
        False if done waiting (counter >= ticks).

    Raises:
        ValueError: If ``ticks`` < 1 or no interaction on the branch.
    """
    if ticks < 1:
        raise ValueError(f"ticks must be >= 1, got {ticks}")
    last = stack.get_last_interaction_for_branch(branch)
    if last is None:
        raise ValueError(f"No interaction found on branch {branch!r}")
    key = f"_wait_ticks_{last.uuid}"
    elapsed = stack.get_shared_state(key, default=0)
    elapsed += 1
    stack.set_shared_state(key, elapsed)
    if elapsed >= ticks:
        try:
            stack.delete_shared_state(key)
        except KeyError:
            logger.warning(
                "wait_for_ticks: shared state key %r already "
                "deleted (possible race condition on branch %r)",
                key,
                branch,
            )
        return False  # Done waiting
    return True  # Keep waiting


@Condition.register()
def wait_for_seconds(
    stack: "Stack", branch: Optional[str], seconds: float
) -> bool:
    """Wait for a specified number of wall-clock seconds.

    Records a timestamp on first evaluation, then checks elapsed time
    on each subsequent call. Returns True (keep waiting) until the
    elapsed time reaches ``seconds``, then returns False (done waiting)
    and cleans up the state key.

    .. note::

        This evaluator mutates shared state on every call. It must
        only be evaluated once per step.

    Args:
        stack: The stack to evaluate the condition on.
        branch: The branch to evaluate the condition on.
        seconds: Wall-clock seconds to wait (must be > 0).

    Returns:
        True if still waiting (elapsed < seconds).
        False if done waiting (elapsed >= seconds).

    Raises:
        ValueError: If ``seconds`` <= 0 or no interaction on the
            branch.
    """
    if seconds <= 0:
        raise ValueError(f"seconds must be > 0, got {seconds}")
    last = stack.get_last_interaction_for_branch(branch)
    if last is None:
        raise ValueError(f"No interaction found on branch {branch!r}")
    key = f"_wait_seconds_{last.uuid}"
    start_time = stack.get_shared_state(key)
    if start_time is None:
        stack.set_shared_state(key, time.time())
        return True  # Just started, keep waiting
    elapsed = time.time() - start_time
    if elapsed >= seconds:
        try:
            stack.delete_shared_state(key)
        except KeyError:
            logger.warning(
                "wait_for_seconds: shared state key %r already "
                "deleted (possible race condition on branch %r)",
                key,
                branch,
            )
        return False  # Done waiting
    return True  # Keep waiting
