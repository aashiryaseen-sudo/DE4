#!/usr/bin/env python3
"""
Proper LangGraph ReAct Agent Implementation (2025)
Based on official LangGraph documentation and patterns
"""

import json
import os
import re
from typing import Annotated, Sequence, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from task_manager import create_task_manager
from xml_editor import create_xml_editor

load_dotenv()


# Define graph state
class AgentState(TypedDict):
    """The state of the agent."""

    messages: Annotated[Sequence[BaseMessage], add_messages]


class XLSFormProperAgent:
    """Proper LangGraph agent implementation for XLSForm editing"""

    def __init__(self, xml_file_path: str):
        self.xml_file_path = xml_file_path

        # Check for OpenAI API key
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")

        # Create tools
        self.tools = self._create_tools()
        self.tools_by_name = {tool.name: tool for tool in self.tools}

        # Initialize model with tools
        self.model = ChatOpenAI(model="gpt-4.1").bind_tools(self.tools)

        # Build the graph
        self.graph = self._build_graph()

    def _create_tools(self):
        """Create tools for the agent"""

        @tool
        def add_choice_option_to_list(list_name: str, label: str, name: str, worksheet: str = "select_multiple") -> str:
            """Add a new choice option to a select_one or select_multiple list in the XLSForm."""
            try:
                # Create the operation for adding a choice option
                operation = {
                    "operation_type": "add",
                    "target_sheet": worksheet,
                    "target_field": name,
                    "choice_option": {"list_name": list_name, "label": label, "name": name, "worksheet": worksheet},
                    "description": f"Add choice option '{label}' (name: '{name}') to list '{list_name}' in worksheet '{worksheet}'",
                }

                # Execute the operation
                xml_editor = create_xml_editor(self.xml_file_path)
                execution_result = xml_editor.execute_operation(operation)

                # Save modified XML if changes were made
                if xml_editor.modified:
                    output_path = xml_editor.save_modified_xml()  # Auto-generates timestamped filename
                    if output_path:
                        execution_result["modified_file_path"] = output_path
                        execution_result["backup_created"] = True
                        return f"✅ SUCCESS: Added choice option '{label}' (name: '{name}') to list '{list_name}' in worksheet '{worksheet}'. Modified file saved as: {output_path}"

                return json.dumps(execution_result, indent=2)

            except Exception as e:
                return f"❌ ERROR: Failed to add choice option: {str(e)}"

        @tool
        def add_choice_options_batch(list_name: str, items_csv: str, worksheet: str = None) -> str:
            """Batch add multiple choice options. Args: list_name, items_csv (comma/period separated labels), worksheet optional.
            The tool auto-detects the correct worksheet by headers; saves once.
            """
            try:
                xml_editor = create_xml_editor(self.xml_file_path)
                # Split on commas or periods
                raw_items = [s.strip() for s in re.split(r"[,\.]+", items_csv) if s.strip()]
                items = [{"label": it, "name": it} for it in raw_items]
                result = xml_editor.add_choice_options_batch(list_name=list_name, items=items, worksheet_name=worksheet)
                if result.get("modified"):
                    output_path = xml_editor.save_modified_xml()
                    return json.dumps(
                        {
                            "success": True,
                            "added": result.get("added"),
                            "failed": result.get("failed"),
                            "modified_file_path": output_path,
                        },
                        indent=2,
                    )
                else:
                    return json.dumps({"success": False, "reason": "no changes"}, indent=2)
            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        @tool
        def analyze_form_structure(worksheet_name: str = None) -> str:
            """Analyze the structure of the XLSForm or a specific worksheet."""
            try:
                from xml_parser import XLSFormParser

                parser = XLSFormParser(self.xml_file_path)
                analysis = parser.analyze_complete_form()

                if worksheet_name:
                    if worksheet_name in analysis:
                        return json.dumps(analysis[worksheet_name], indent=2)
                    else:
                        return f"Worksheet '{worksheet_name}' not found. Available worksheets: {list(analysis.keys())}"
                else:
                    return json.dumps(analysis, indent=2)

            except Exception as e:
                return f"❌ ERROR: Failed to analyze form structure: {str(e)}"

        @tool
        def add_row_auto(target_sheet_hint: str, row_values_csv: str) -> str:
            """Add a row to the best matching worksheet by headers. Args: target_sheet_hint (can be 'settings' or empty), row_values_csv."""
            try:
                xml_editor = create_xml_editor(self.xml_file_path)
                values = [s.strip() for s in re.split(r",+", row_values_csv) if s.strip()]
                result = xml_editor.add_row_to_best_match(values, sheet_hint=target_sheet_hint or None)
                if result.get("success"):
                    out = xml_editor.save_modified_xml()
                    return json.dumps(
                        {"success": True, "worksheet": result.get("worksheet"), "modified_file_path": out}, indent=2
                    )
                return json.dumps(result, indent=2)
            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        @tool
        def create_task_plan(user_prompt: str) -> str:
            """Create a task plan for complex operations. Shows TODO-like breakdown before execution."""
            try:
                task_manager = create_task_manager(self.xml_file_path)
                session = task_manager.create_task_session(user_prompt)
                return json.dumps(
                    {
                        "task_plan_created": True,
                        "session_id": session["session_id"],
                        "total_tasks": session["total_tasks"],
                        "tasks_breakdown": session["tasks"],
                        "estimated_time": session["estimated_time"],
                        "message": "📋 Task plan ready! Review the tasks above. Use execute_task_plan to proceed.",
                    },
                    indent=2,
                )
            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        @tool
        def execute_task_plan(session_id: str, confirm: bool = True) -> str:
            """Execute a previously created task plan with progress tracking."""
            try:
                task_manager = create_task_manager(self.xml_file_path)
                # Note: In production, we'd need session persistence
                # For now, we'll re-create and execute immediately
                result = task_manager.execute_task_session(confirm)
                return json.dumps(
                    {
                        "execution_completed": True,
                        "status": result["status"],
                        "completed_tasks": result["completed_tasks"],
                        "failed_tasks": result["failed_tasks"],
                        "modified_files": result["modified_files"],
                        "execution_time": result["execution_time"],
                        "detailed_results": result["results"],
                    },
                    indent=2,
                )
            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        @tool
        def delete_field(field_name: str) -> str:
            """Deletes a field (a single row) from the 'survey' worksheet using its unique field name."""
            try:
                xml_editor = create_xml_editor(self.xml_file_path)
                success = xml_editor.remove_field_by_name(field_name)

                if success and xml_editor.modified:
                    output_path = xml_editor.save_modified_xml()
                    return json.dumps(
                        {
                            "success": True,
                            "message": f"Field '{field_name}' and its associated choices were successfully deleted.",
                            "modified_file_path": output_path,
                        },
                        indent=2,
                    )
                elif not success:
                    return json.dumps(
                        {
                            "success": False,
                            "message": f"Failed to delete field '{field_name}'. It may not exist in the 'survey' sheet.",
                        },
                        indent=2,
                    )
                else:
                    return json.dumps(
                        {"success": True, "message": "Delete operation was successful but no changes were saved."}
                    )

            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        @tool
        def modify_field_property(field_name: str, property_name: str, new_value: str) -> str:
            """Modifies a single property of an existing field in the 'survey' worksheet."""
            try:
                xml_editor = create_xml_editor(self.xml_file_path)
                success = xml_editor.modify_field_property(field_name, property_name, new_value)

                if success and xml_editor.modified:
                    output_path = xml_editor.save_modified_xml()
                    return json.dumps(
                        {
                            "success": True,
                            "message": f"Property '{property_name}' for field '{field_name}' was successfully updated.",
                            "modified_file_path": output_path,
                        },
                        indent=2,
                    )
                elif not success:
                    return json.dumps(
                        {
                            "success": False,
                            "message": f"Failed to modify property '{property_name}' for field '{field_name}'.",
                        },
                        indent=2,
                    )
                else:
                    return json.dumps(
                        {"success": True, "message": "Modification was successful but no changes were saved."}
                    )

            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        return [
            add_choice_option_to_list,
            add_choice_options_batch,
            add_row_auto,
            create_task_plan,
            execute_task_plan,
            analyze_form_structure,
            delete_field,
            modify_field_property,
        ]

    def _build_graph(self):
        """Build the LangGraph workflow"""

        def tool_node(state: AgentState):
            """Handle tool calls."""
            outputs = []
            last_message = state["messages"][-1]

            for tool_call in last_message.tool_calls:
                print(f"🔧 Executing tool: {tool_call['name']} with args: {tool_call['args']}")

                try:
                    tool_result = self.tools_by_name[tool_call["name"]].invoke(tool_call["args"])
                    print(f"✅ Tool result: {tool_result}")

                    outputs.append(
                        ToolMessage(
                            content=str(tool_result),
                            name=tool_call["name"],
                            tool_call_id=tool_call["id"],
                        )
                    )
                except Exception as e:
                    print(f"❌ Tool execution error: {e}")
                    outputs.append(
                        ToolMessage(
                            content=f"Error executing tool: {str(e)}",
                            name=tool_call["name"],
                            tool_call_id=tool_call["id"],
                        )
                    )

            return {"messages": outputs}

        def call_model(state: AgentState, config: RunnableConfig):
            """Invoke the model with system prompt and current state."""
            system_prompt = SystemMessage(
                """You are an XLSForm editor with task management capabilities. 

For COMPLEX operations (multiple items, multiple sheets, or multi-step requests):
1. First use create_task_plan to break down the request into manageable tasks
2. Then use execute_task_plan to perform the operations with progress tracking

For SIMPLE operations (single addition, single modification):
- Use the direct tools (add_choice_option_to_list, add_row_auto, etc.)

Always prioritize task management for complex requests to prevent errors and file explosion."""
            )

            response = self.model.invoke([system_prompt] + state["messages"], config)
            print(f"🤖 Model response: {response.content}")
            if hasattr(response, "tool_calls") and response.tool_calls:
                print(f"🔧 Model wants to call {len(response.tool_calls)} tools")

            return {"messages": [response]}

        def should_continue(state: AgentState):
            """Determine if the agent should continue to tools or end."""
            last_message = state["messages"][-1]
            has_tool_calls = hasattr(last_message, "tool_calls") and last_message.tool_calls
            print(f"🤔 Should continue? Has tool calls: {has_tool_calls}")
            return "continue" if has_tool_calls else "end"

        # Define and compile the graph
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {"continue": "tools", "end": END},
        )
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    async def process_prompt(self, user_prompt: str):
        """Process user prompt using the proper LangGraph agent"""
        print(f"🚀 Processing prompt: '{user_prompt}'")

        inputs = {"messages": [("user", user_prompt)]}

        try:
            result_messages = []
            for step in self.graph.stream(inputs, stream_mode="values"):
                if "messages" in step:
                    result_messages.extend(step["messages"])

            # Extract the final response
            final_response = ""
            tool_calls_made = 0

            for msg in result_messages:
                if hasattr(msg, "content") and msg.content:
                    final_response += str(msg.content) + "\n"
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_calls_made += len(msg.tool_calls)

            return {
                "success": True,
                "user_prompt": user_prompt,
                "agent_response": final_response.strip(),
                "tool_calls_made": tool_calls_made,
                "messages": result_messages,
            }

        except Exception as e:
            return {"success": False, "error": str(e), "user_prompt": user_prompt}


def create_proper_xlsform_agent(xml_file_path: str):
    """Factory function to create the proper XLSForm agent"""
    return XLSFormProperAgent(xml_file_path)
