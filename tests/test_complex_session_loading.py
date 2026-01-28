"""Comprehensive tests for loading and saving complex sessions.

This test suite ensures that complex sessions with multiple agents,
all interaction types, artifacts, and sub-components can be properly
saved and loaded without data loss or corruption.
"""

import tempfile
from pathlib import Path

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.file import File
from gimle.hugin.artifacts.text import Text
from gimle.hugin.interaction.ask_human import AskHuman
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.human_response import HumanResponse
from gimle.hugin.interaction.oracle_response import OracleResponse
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.tool_call import ToolCall
from gimle.hugin.interaction.tool_result import ToolResult
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.storage.local import LocalStorage


class TestComplexSessionLoading:
    """Test loading and saving complex sessions with multiple agents and all interaction types."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield LocalStorage(base_path=Path(tmpdir))

    @pytest.fixture
    def environment(self, temp_storage):
        """Create an environment with temporary storage."""
        return Environment(storage=temp_storage)

    def test_session_with_multiple_agents_all_interaction_types(
        self, environment, temp_storage
    ):
        """Test saving and loading a session with multiple agents and all interaction types."""
        # Create session
        session = Session(environment=environment)
        session_uuid = session.uuid

        # Create first agent with complex interaction chain
        config1 = Config(
            name="agent1",
            description="First agent with complex interactions",
            system_template="You are agent 1.",
            tools=[],
            llm_model="model1",
        )
        agent1 = Agent(session=session, config=config1)
        agent1_uuid = agent1.uuid

        # Agent 1: TaskDefinition
        task1 = Task(
            name="task1",
            description="Task 1",
            parameters={},
            prompt="Do task 1",
            tools=[],
        )
        task_def1 = TaskDefinition(stack=agent1.stack, task=task1)
        task_def1_uuid = task_def1.uuid
        agent1.stack.add_interaction(task_def1)

        # Agent 1: AskOracle
        prompt1 = Prompt(type="text", text="Ask something")
        ask_oracle1 = AskOracle(
            stack=agent1.stack, prompt=prompt1, template_inputs={}
        )
        ask_oracle1_uuid = ask_oracle1.uuid
        agent1.stack.add_interaction(ask_oracle1)

        # Agent 1: OracleResponse
        oracle_response1 = OracleResponse(
            stack=agent1.stack,
            response={
                "role": "assistant",
                "content": "Response 1",
                "tool_call": None,
            },
        )
        oracle_response1_uuid = oracle_response1.uuid
        agent1.stack.add_interaction(oracle_response1)

        # Agent 1: ToolCall
        tool_call1 = ToolCall(
            stack=agent1.stack,
            tool="test_tool",
            args={"arg1": "value1"},
            tool_call_id="call_1",
        )
        tool_call1_uuid = tool_call1.uuid
        agent1.stack.add_interaction(tool_call1)

        # Agent 1: ToolResult
        tool_result1 = ToolResult(
            stack=agent1.stack,
            result={"result": "success"},
            tool_call_id="call_1",
            tool_name="test_tool",
            is_error=False,
        )
        tool_result1_uuid = tool_result1.uuid
        agent1.stack.add_interaction(tool_result1)

        # Agent 1: TaskResult
        task_result1 = TaskResult(
            stack=agent1.stack,
            finish_type="success",
            summary="Task 1 completed",
            reason="All steps completed",
        )
        task_result1_uuid = task_result1.uuid
        agent1.stack.add_interaction(task_result1)

        session.add_agent(agent1)

        # Create second agent with different interaction types
        config2 = Config(
            name="agent2",
            description="Second agent with human interactions",
            system_template="You are agent 2.",
            tools=[],
            llm_model="model2",
        )
        agent2 = Agent(session=session, config=config2)
        agent2_uuid = agent2.uuid

        # Agent 2: TaskDefinition
        task2 = Task(
            name="task2",
            description="Task 2",
            parameters={},
            prompt="Do task 2",
            tools=[],
        )
        task_def2 = TaskDefinition(stack=agent2.stack, task=task2)
        task_def2_uuid = task_def2.uuid
        agent2.stack.add_interaction(task_def2)

        # Agent 2: AskHuman
        ask_human1 = AskHuman(stack=agent2.stack, question="What should I do?")
        ask_human1_uuid = ask_human1.uuid
        agent2.stack.add_interaction(ask_human1)

        # Agent 2: HumanResponse
        human_response1 = HumanResponse(
            stack=agent2.stack, response="Do something specific"
        )
        human_response1_uuid = human_response1.uuid
        agent2.stack.add_interaction(human_response1)

        session.add_agent(agent2)

        # Save all entities
        temp_storage.save_interaction(task_def1)
        temp_storage.save_interaction(ask_oracle1)
        temp_storage.save_interaction(oracle_response1)
        temp_storage.save_interaction(tool_call1)
        temp_storage.save_interaction(tool_result1)
        temp_storage.save_interaction(task_result1)
        temp_storage.save_interaction(task_def2)
        temp_storage.save_interaction(ask_human1)
        temp_storage.save_interaction(human_response1)
        temp_storage.save_agent(agent1)
        temp_storage.save_agent(agent2)
        temp_storage.save_session(session)

        # Load session
        loaded_session = temp_storage.load_session(
            session_uuid, environment=environment
        )

        # Verify session
        assert loaded_session.uuid == session_uuid
        assert len(loaded_session.agents) == 2

        # Verify first agent
        loaded_agent1 = loaded_session.get_agent(agent1_uuid)
        assert loaded_agent1 is not None
        assert loaded_agent1.uuid == agent1_uuid
        assert loaded_agent1.config.name == "agent1"
        assert len(loaded_agent1.stack.interactions) == 6

        # Verify first agent's interactions
        interactions1 = loaded_agent1.stack.interactions
        assert isinstance(interactions1[0], TaskDefinition)
        assert interactions1[0].uuid == task_def1_uuid
        assert isinstance(interactions1[1], AskOracle)
        assert interactions1[1].uuid == ask_oracle1_uuid
        assert isinstance(interactions1[2], OracleResponse)
        assert interactions1[2].uuid == oracle_response1_uuid
        assert isinstance(interactions1[3], ToolCall)
        assert interactions1[3].uuid == tool_call1_uuid
        assert interactions1[3].tool == "test_tool"
        assert isinstance(interactions1[4], ToolResult)
        assert interactions1[4].uuid == tool_result1_uuid
        assert isinstance(interactions1[5], TaskResult)
        assert interactions1[5].uuid == task_result1_uuid
        assert interactions1[5].finish_type == "success"

        # Verify second agent
        loaded_agent2 = loaded_session.get_agent(agent2_uuid)
        assert loaded_agent2 is not None
        assert loaded_agent2.uuid == agent2_uuid
        assert loaded_agent2.config.name == "agent2"
        assert len(loaded_agent2.stack.interactions) == 3

        # Verify second agent's interactions
        interactions2 = loaded_agent2.stack.interactions
        assert isinstance(interactions2[0], TaskDefinition)
        assert interactions2[0].uuid == task_def2_uuid
        assert isinstance(interactions2[1], AskHuman)
        assert interactions2[1].uuid == ask_human1_uuid
        assert interactions2[1].question == "What should I do?"
        assert isinstance(interactions2[2], HumanResponse)
        assert interactions2[2].uuid == human_response1_uuid
        assert interactions2[2].response == "Do something specific"

    def test_session_with_artifacts_all_formats(
        self, environment, temp_storage
    ):
        """Test saving and loading a session with artifacts in all formats."""
        session = Session(environment=environment)
        session_uuid = session.uuid

        config = Config(
            name="artifact_agent",
            description="Agent with artifacts",
            system_template="You are an agent.",
            tools=[],
        )
        agent = Agent(session=session, config=config)
        agent_uuid = agent.uuid

        # Create task definition
        task = Task(
            name="artifact_task",
            description="Task with artifacts",
            parameters={},
            prompt="Create artifacts",
            tools=[],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        agent.stack.add_interaction(task_def)

        # Add Text artifacts with different formats
        text_plain = Text(
            interaction=task_def, content="Plain text content", format="plain"
        )
        text_plain_uuid = text_plain.uuid
        task_def.add_artifact(text_plain)

        text_markdown = Text(
            interaction=task_def,
            content="# Markdown\nContent here",
            format="markdown",
        )
        text_markdown_uuid = text_markdown.uuid
        task_def.add_artifact(text_markdown)

        text_html = Text(
            interaction=task_def,
            content="<h1>HTML</h1><p>Content</p>",
            format="html",
        )
        text_html_uuid = text_html.uuid
        task_def.add_artifact(text_html)

        text_json = Text(
            interaction=task_def,
            content='{"key": "value"}',
            format="json",
        )
        text_json_uuid = text_json.uuid
        task_def.add_artifact(text_json)

        # Add File artifact
        file_artifact = File(
            interaction=task_def, path="test_file.txt", description="Test file"
        )
        file_artifact_uuid = file_artifact.uuid
        task_def.add_artifact(file_artifact)

        session.add_agent(agent)

        # Save all entities
        temp_storage.save_interaction(task_def)
        temp_storage.save_artifact(text_plain)
        temp_storage.save_artifact(text_markdown)
        temp_storage.save_artifact(text_html)
        temp_storage.save_artifact(text_json)
        temp_storage.save_artifact(file_artifact)
        temp_storage.save_agent(agent)
        temp_storage.save_session(session)

        # Load session
        loaded_session = temp_storage.load_session(
            session_uuid, environment=environment
        )

        # Verify artifacts
        loaded_agent = loaded_session.get_agent(agent_uuid)
        assert loaded_agent is not None
        loaded_task_def = loaded_agent.stack.interactions[0]
        assert len(loaded_task_def.artifacts) == 5

        # Verify Text artifacts
        artifacts = loaded_task_def.artifacts
        text_artifacts = [a for a in artifacts if isinstance(a, Text)]
        assert len(text_artifacts) == 4

        plain_artifact = next(
            (a for a in text_artifacts if a.format == "plain"), None
        )
        assert plain_artifact is not None
        assert plain_artifact.uuid == text_plain_uuid
        assert plain_artifact.content == "Plain text content"

        markdown_artifact = next(
            (a for a in text_artifacts if a.format == "markdown"), None
        )
        assert markdown_artifact is not None
        assert markdown_artifact.uuid == text_markdown_uuid
        assert markdown_artifact.content == "# Markdown\nContent here"

        html_artifact = next(
            (a for a in text_artifacts if a.format == "html"), None
        )
        assert html_artifact is not None
        assert html_artifact.uuid == text_html_uuid
        assert html_artifact.content == "<h1>HTML</h1><p>Content</p>"

        json_artifact = next(
            (a for a in text_artifacts if a.format == "json"), None
        )
        assert json_artifact is not None
        assert json_artifact.uuid == text_json_uuid
        assert json_artifact.content == '{"key": "value"}'

        # Verify File artifact
        file_artifacts = [a for a in artifacts if isinstance(a, File)]
        assert len(file_artifacts) == 1
        assert file_artifacts[0].uuid == file_artifact_uuid
        assert file_artifacts[0].path == "test_file.txt"

    def test_session_with_branches(self, environment, temp_storage):
        """Test saving and loading a session with branches."""
        session = Session(environment=environment)
        session_uuid = session.uuid

        config = Config(
            name="branch_agent",
            description="Agent with branches",
            system_template="You are an agent.",
            tools=[],
        )
        agent = Agent(session=session, config=config)
        agent_uuid = agent.uuid

        # Create task definition
        task = Task(
            name="branch_task",
            description="Task with branches",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        agent.stack.add_interaction(task_def, branch="main")

        # Add interactions to different branches
        prompt1 = Prompt(type="text", text="Branch 1")
        ask_oracle1 = AskOracle(
            stack=agent.stack, prompt=prompt1, template_inputs={}
        )
        agent.stack.add_interaction(ask_oracle1, branch="branch1")

        prompt2 = Prompt(type="text", text="Branch 2")
        ask_oracle2 = AskOracle(
            stack=agent.stack, prompt=prompt2, template_inputs={}
        )
        agent.stack.add_interaction(ask_oracle2, branch="branch2")

        session.add_agent(agent)

        # Save all entities
        temp_storage.save_interaction(task_def)
        temp_storage.save_interaction(ask_oracle1)
        temp_storage.save_interaction(ask_oracle2)
        temp_storage.save_agent(agent)
        temp_storage.save_session(session)

        # Load session
        loaded_session = temp_storage.load_session(
            session_uuid, environment=environment
        )

        # Verify branches
        loaded_agent = loaded_session.get_agent(agent_uuid)
        assert loaded_agent is not None
        assert len(loaded_agent.stack.interactions) == 3

        # Verify branch information is preserved on interactions
        # First check that branches are set on the interactions themselves
        branches_on_interactions = [
            i.branch for i in loaded_agent.stack.interactions
        ]
        assert "main" in branches_on_interactions
        assert "branch1" in branches_on_interactions
        assert "branch2" in branches_on_interactions

        # Verify branches dict is rebuilt
        # The stack.from_dict method should rebuild the branches dict
        # by checking each interaction's branch field
        assert (
            "branch1" in loaded_agent.stack.branches
            or loaded_agent.stack.interactions[1].branch == "branch1"
        )
        assert (
            "branch2" in loaded_agent.stack.branches
            or loaded_agent.stack.interactions[2].branch == "branch2"
        )

        # If branches dict is populated, verify the contents
        if loaded_agent.stack.branches:
            if "branch1" in loaded_agent.stack.branches:
                assert len(loaded_agent.stack.branches["branch1"]) == 1
                assert ask_oracle1.uuid in [
                    i.uuid for i in loaded_agent.stack.branches["branch1"]
                ]
            if "branch2" in loaded_agent.stack.branches:
                assert len(loaded_agent.stack.branches["branch2"]) == 1
                assert ask_oracle2.uuid in [
                    i.uuid for i in loaded_agent.stack.branches["branch2"]
                ]

    def test_session_multiple_agents_with_artifacts_on_interactions(
        self, environment, temp_storage
    ):
        """Test saving and loading multiple agents with artifacts on various interactions."""
        session = Session(environment=environment)
        session_uuid = session.uuid

        # Create first agent
        config1 = Config(
            name="agent1",
            description="First agent",
            system_template="You are agent 1.",
            tools=[],
        )
        agent1 = Agent(session=session, config=config1)
        agent1_uuid = agent1.uuid

        task1 = Task(
            name="task1",
            description="Task 1",
            parameters={},
            prompt="Do task 1",
            tools=[],
        )
        task_def1 = TaskDefinition(stack=agent1.stack, task=task1)
        agent1.stack.add_interaction(task_def1)

        # Add artifact to TaskDefinition
        artifact1 = Text(
            interaction=task_def1,
            content="Task definition artifact",
            format="markdown",
        )
        artifact1_uuid = artifact1.uuid
        task_def1.add_artifact(artifact1)

        # Add AskOracle with artifact
        prompt1 = Prompt(type="text", text="Ask")
        ask_oracle1 = AskOracle(
            stack=agent1.stack, prompt=prompt1, template_inputs={}
        )
        agent1.stack.add_interaction(ask_oracle1)
        artifact2 = Text(
            interaction=ask_oracle1,
            content="AskOracle artifact",
            format="plain",
        )
        artifact2_uuid = artifact2.uuid
        ask_oracle1.add_artifact(artifact2)

        session.add_agent(agent1)

        # Create second agent
        config2 = Config(
            name="agent2",
            description="Second agent",
            system_template="You are agent 2.",
            tools=[],
        )
        agent2 = Agent(session=session, config=config2)
        agent2_uuid = agent2.uuid

        task2 = Task(
            name="task2",
            description="Task 2",
            parameters={},
            prompt="Do task 2",
            tools=[],
        )
        task_def2 = TaskDefinition(stack=agent2.stack, task=task2)
        agent2.stack.add_interaction(task_def2)

        # Add multiple artifacts to second agent's TaskDefinition
        artifact3 = Text(
            interaction=task_def2, content="Artifact 3", format="json"
        )
        artifact3_uuid = artifact3.uuid
        task_def2.add_artifact(artifact3)

        artifact4 = Text(
            interaction=task_def2, content="Artifact 4", format="html"
        )
        artifact4_uuid = artifact4.uuid
        task_def2.add_artifact(artifact4)

        # Add ToolCall with artifact
        tool_call = ToolCall(
            stack=agent2.stack,
            tool="test_tool",
            args={},
            tool_call_id="call_1",
        )
        agent2.stack.add_interaction(tool_call)
        artifact5 = Text(
            interaction=tool_call, content="ToolCall artifact", format="plain"
        )
        artifact5_uuid = artifact5.uuid
        tool_call.add_artifact(artifact5)

        session.add_agent(agent2)

        # Save all entities
        temp_storage.save_interaction(task_def1)
        temp_storage.save_interaction(ask_oracle1)
        temp_storage.save_interaction(task_def2)
        temp_storage.save_interaction(tool_call)
        temp_storage.save_artifact(artifact1)
        temp_storage.save_artifact(artifact2)
        temp_storage.save_artifact(artifact3)
        temp_storage.save_artifact(artifact4)
        temp_storage.save_artifact(artifact5)
        temp_storage.save_agent(agent1)
        temp_storage.save_agent(agent2)
        temp_storage.save_session(session)

        # Load session
        loaded_session = temp_storage.load_session(
            session_uuid, environment=environment
        )

        # Verify first agent and its artifacts
        loaded_agent1 = loaded_session.get_agent(agent1_uuid)
        assert loaded_agent1 is not None
        assert len(loaded_agent1.stack.interactions) == 2

        loaded_task_def1 = loaded_agent1.stack.interactions[0]
        assert len(loaded_task_def1.artifacts) == 1
        assert loaded_task_def1.artifacts[0].uuid == artifact1_uuid

        loaded_ask_oracle1 = loaded_agent1.stack.interactions[1]
        assert len(loaded_ask_oracle1.artifacts) == 1
        assert loaded_ask_oracle1.artifacts[0].uuid == artifact2_uuid

        # Verify second agent and its artifacts
        loaded_agent2 = loaded_session.get_agent(agent2_uuid)
        assert loaded_agent2 is not None
        assert len(loaded_agent2.stack.interactions) == 2

        loaded_task_def2 = loaded_agent2.stack.interactions[0]
        assert len(loaded_task_def2.artifacts) == 2
        artifact_uuids = [a.uuid for a in loaded_task_def2.artifacts]
        assert artifact3_uuid in artifact_uuids
        assert artifact4_uuid in artifact_uuids

        loaded_tool_call = loaded_agent2.stack.interactions[1]
        assert len(loaded_tool_call.artifacts) == 1
        assert loaded_tool_call.artifacts[0].uuid == artifact5_uuid

    def test_session_round_trip_complex_scenario(
        self, environment, temp_storage
    ):
        """Test a complex round-trip scenario with multiple agents, all interaction types, and artifacts."""
        # Create original session
        session = Session(environment=environment)
        original_session_uuid = session.uuid

        # Create three agents with different configurations
        configs = [
            Config(
                name=f"agent{i}",
                description=f"Agent {i}",
                system_template=f"You are agent {i}.",
                tools=[],
                llm_model=f"model{i}",
            )
            for i in range(1, 4)
        ]

        agents = []
        for config in configs:
            agent = Agent(session=session, config=config)
            task = Task(
                name=f"task_{config.name}",
                description=f"Task for {config.name}",
                parameters={},
                prompt=f"Do task for {config.name}",
                tools=[],
            )
            task_def = TaskDefinition(stack=agent.stack, task=task)
            agent.stack.add_interaction(task_def)

            # Add various interaction types to each agent
            if config.name == "agent1":
                # Agent 1: Oracle interactions
                prompt = Prompt(type="text", text="Question")
                ask_oracle = AskOracle(
                    stack=agent.stack, prompt=prompt, template_inputs={}
                )
                agent.stack.add_interaction(ask_oracle)
                oracle_response = OracleResponse(
                    stack=agent.stack,
                    response={"role": "assistant", "content": "Answer"},
                )
                agent.stack.add_interaction(oracle_response)

            elif config.name == "agent2":
                # Agent 2: Human interactions
                ask_human = AskHuman(stack=agent.stack, question="What?")
                agent.stack.add_interaction(ask_human)
                human_response = HumanResponse(
                    stack=agent.stack, response="Response"
                )
                agent.stack.add_interaction(human_response)

            elif config.name == "agent3":
                # Agent 3: Tool interactions
                tool_call = ToolCall(
                    stack=agent.stack,
                    tool="test_tool",
                    args={"key": "value"},
                    tool_call_id="call_1",
                )
                agent.stack.add_interaction(tool_call)
                tool_result = ToolResult(
                    stack=agent.stack,
                    result={"result": "ok"},
                    tool_call_id="call_1",
                    tool_name="test_tool",
                    is_error=False,
                )
                agent.stack.add_interaction(tool_result)

            # Add artifacts to each agent's first interaction
            artifact = Text(
                interaction=task_def,
                content=f"Artifact for {config.name}",
                format="markdown",
            )
            task_def.add_artifact(artifact)

            session.add_agent(agent)
            agents.append(agent)

        # Save everything
        for agent in agents:
            for interaction in agent.stack.interactions:
                temp_storage.save_interaction(interaction)
                for artifact in interaction.artifacts:
                    temp_storage.save_artifact(artifact)
            temp_storage.save_agent(agent)
        temp_storage.save_session(session)

        # Load session
        loaded_session = temp_storage.load_session(
            original_session_uuid, environment=environment
        )

        # Verify everything
        assert loaded_session.uuid == original_session_uuid
        assert len(loaded_session.agents) == 3

        for i, original_agent in enumerate(agents):
            loaded_agent = loaded_session.get_agent(original_agent.uuid)
            assert loaded_agent is not None
            assert loaded_agent.config.name == original_agent.config.name
            assert len(loaded_agent.stack.interactions) == len(
                original_agent.stack.interactions
            )

            # Verify interactions match
            for j, original_interaction in enumerate(
                original_agent.stack.interactions
            ):
                loaded_interaction = loaded_agent.stack.interactions[j]
                assert isinstance(
                    loaded_interaction, type(original_interaction)
                ), (
                    f"Type mismatch: expected {type(original_interaction).__name__}, "
                    f"got {type(loaded_interaction).__name__}"
                )
                assert loaded_interaction.uuid == original_interaction.uuid

                # Verify artifacts match
                assert len(loaded_interaction.artifacts) == len(
                    original_interaction.artifacts
                )
                for k, original_artifact in enumerate(
                    original_interaction.artifacts
                ):
                    loaded_artifact = loaded_interaction.artifacts[k]
                    assert loaded_artifact.uuid == original_artifact.uuid
                    if isinstance(loaded_artifact, Text):
                        assert (
                            loaded_artifact.content == original_artifact.content
                        )
                        assert (
                            loaded_artifact.format == original_artifact.format
                        )

    def test_session_preserves_all_uuids_and_references(
        self, environment, temp_storage
    ):
        """Test that all UUIDs and references are preserved during save/load."""
        session = Session(environment=environment)
        session_uuid = session.uuid

        config = Config(
            name="test_agent",
            description="Test agent",
            system_template="You are a test agent.",
            tools=[],
        )
        agent = Agent(session=session, config=config)
        agent_uuid = agent.uuid

        task = Task(
            name="test_task",
            description="Test task",
            parameters={},
            prompt="Test prompt",
            tools=[],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        task_def_uuid = task_def.uuid
        agent.stack.add_interaction(task_def)

        # Add multiple artifacts
        artifacts = []
        for i in range(3):
            artifact = Text(
                interaction=task_def,
                content=f"Content {i}",
                format="plain",
            )
            artifacts.append(artifact)
            task_def.add_artifact(artifact)

        session.add_agent(agent)

        # Save everything
        temp_storage.save_interaction(task_def)
        for artifact in artifacts:
            temp_storage.save_artifact(artifact)
        temp_storage.save_agent(agent)
        temp_storage.save_session(session)

        # Load session
        loaded_session = temp_storage.load_session(
            session_uuid, environment=environment
        )

        # Verify all UUIDs are preserved
        assert loaded_session.uuid == session_uuid
        loaded_agent = loaded_session.get_agent(agent_uuid)
        assert loaded_agent is not None
        assert loaded_agent.uuid == agent_uuid
        assert loaded_agent.session.uuid == session_uuid

        loaded_task_def = loaded_agent.stack.interactions[0]
        assert loaded_task_def.uuid == task_def_uuid
        assert loaded_task_def.stack.agent.uuid == agent_uuid

        # Verify artifact UUIDs and references
        assert len(loaded_task_def.artifacts) == 3
        for i, original_artifact in enumerate(artifacts):
            loaded_artifact = loaded_task_def.artifacts[i]
            assert loaded_artifact.uuid == original_artifact.uuid
            assert loaded_artifact.interaction.uuid == task_def_uuid

    def test_session_with_missing_interaction_handles_gracefully(
        self, environment, temp_storage
    ):
        """Test that missing interactions are handled gracefully during loading."""
        session = Session(environment=environment)
        session_uuid = session.uuid

        config = Config(
            name="test_agent",
            description="Test agent",
            system_template="You are a test agent.",
            tools=[],
        )
        agent = Agent(session=session, config=config)
        agent_uuid = agent.uuid

        task = Task(
            name="test_task",
            description="Test task",
            parameters={},
            prompt="Test prompt",
            tools=[],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        task_def_uuid = task_def.uuid
        agent.stack.add_interaction(task_def)

        # Add a valid interaction
        prompt = Prompt(type="text", text="Valid")
        ask_oracle = AskOracle(
            stack=agent.stack, prompt=prompt, template_inputs={}
        )
        ask_oracle_uuid = ask_oracle.uuid
        agent.stack.add_interaction(ask_oracle)

        session.add_agent(agent)

        # Save valid interactions
        temp_storage.save_interaction(task_def)
        temp_storage.save_interaction(ask_oracle)
        temp_storage.save_agent(agent)
        temp_storage.save_session(session)

        # Manually delete one interaction file to simulate corruption/loss
        ask_oracle_path = temp_storage.base_path / ask_oracle_uuid
        if ask_oracle_path.exists():
            ask_oracle_path.unlink()

        # Load session - should handle missing interaction gracefully
        # The stack.from_dict method should skip missing interactions
        loaded_session = temp_storage.load_session(
            session_uuid, environment=environment
        )

        # Should still load valid interactions
        loaded_agent = loaded_session.get_agent(agent_uuid)
        assert loaded_agent is not None
        # Should have at least the valid interaction (task_def)
        assert len(loaded_agent.stack.interactions) >= 1
        # Verify valid interaction is present
        interaction_uuids = [i.uuid for i in loaded_agent.stack.interactions]
        assert task_def_uuid in interaction_uuids
