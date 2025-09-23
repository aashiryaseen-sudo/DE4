#!/usr/bin/env python3
"""
Proper LangGraph ReAct Agent Implementation (2025)
Based on official LangGraph documentation and patterns
"""

import json
import os
import re
import tempfile
from datetime import datetime
from typing import Annotated, Sequence, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from database import get_database_session
from database_schema import FormVersion, MasterForm
from task_manager import create_task_manager
from xml_editor import create_xml_editor

load_dotenv()


# Define graph state
class AgentState(TypedDict):
    """The state of the agent."""

    messages: Annotated[Sequence[BaseMessage], add_messages]


class XLSFormProperAgent:
    """Proper LangGraph agent implementation for XLSForm editing"""

    def __init__(self, xml_file_path: str, base_original_path: str = None):
        self.xml_file_path = xml_file_path
        self.base_original_path = base_original_path or xml_file_path

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
        def clone_form_with_filter(new_form_name: str, equipment_list_csv: str) -> str:
            """Clones the current master form but includes ONLY the equipment sections specified.
            Args:
                new_form_name (str): The desired title and ID for the new form.
                equipment_list_csv (str): A comma-separated list of the equipment_type values to KEEP.
            """
            try:
                editor = create_xml_editor(self.xml_file_path, base_original_path=self.base_original_path)
                equipment_to_keep = [e.strip() for e in equipment_list_csv.split(",") if e.strip()]

                output_path = editor.clone_and_filter_by_equipment(new_form_name, equipment_to_keep)

                if output_path:
                    return json.dumps(
                        {
                            "success": True,
                            "message": f"Successfully cloned form with {len(equipment_to_keep)} equipment types.",
                            "new_form_path": output_path,
                        },
                        indent=2,
                    )
                else:
                    return json.dumps({"success": False, "error": "Cloning process failed."})

            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        @tool
        def merge_forms_from_db(source_form_name: str, destination_form_name: str, field_names_csv: str) -> str:
            """
            Copies specified fields (and their choices) from a source form into a destination form.
            This tool searches the database for both forms, copies the data, and saves a new file.
            Args:
                source_form_name (str): The name (form_title) of the form to COPY FROM.
                destination_form_name (str): The name (form_title) of the form to COPY TO.
                field_names_csv (str): A comma-separated list of field names or labels to copy.
            """
            from main import decompress_xml_from_base64

            print(f"🚀 Executing merge_forms_from_db...")
            db = next(get_database_session())
            try:
                # 1. Get Source Form XML
                source_master = db.query(MasterForm).filter(MasterForm.name == source_form_name).first()
                if not source_master:
                    return json.dumps({"success": False, "error": f"Source form '{source_form_name}' not found."})

                source_version = (
                    db.query(FormVersion)
                    .filter(FormVersion.master_form_id == source_master.id, FormVersion.is_current == True)
                    .first()
                )
                if not source_version:
                    return json.dumps(
                        {"success": False, "error": f"No 'current' version found for source form '{source_form_name}'."}
                    )

                source_xml = decompress_xml_from_base64(source_version.xml_content)
                if not source_xml:
                    return json.dumps(
                        {"success": False, "error": f"Source form '{source_form_name}' has no XML content."}
                    )

                # 2. Get Destination Form XML (using the agent's current file)
                # The 'destination' is the file already loaded into the agent
                if not os.path.exists(self.xml_file_path):
                    return json.dumps(
                        {"success": False, "error": f"Destination file path not valid: {self.xml_file_path}"}
                    )

                # 3. Save source XML to a temp file for the editor
                with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".xml", encoding="utf-8") as f:
                    f.write(source_xml)
                    source_temp_path = f.name

                print(f"🔍 Source XML saved to temp file: {source_temp_path}")

                # 4. Initialize editor with the DESTINATION file
                editor = create_xml_editor(self.xml_file_path, base_original_path=self.base_original_path)

                # 5. Call the new merge function
                fields_to_copy = [f.strip() for f in field_names_csv.split(",") if f.strip()]
                merge_result = editor.merge_fields_from_source(source_temp_path, fields_to_copy)

                os.remove(source_temp_path)  # Clean up temp file

                if not merge_result.get("success"):
                    return json.dumps(merge_result)

                # 6. Save the newly merged file
                new_name_base = destination_form_name.replace(" ", "_").replace(".xml", "")

                original_dir = os.path.dirname(self.base_original_path)

                new_filename = f"modified_MERGE_{new_name_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
                output_path = os.path.join(original_dir, new_filename)

                output_path = editor.save_modified_xml(output_path=output_path)

                return json.dumps(
                    {
                        "success": True,
                        "message": f"Successfully merged {merge_result.get('fields_copied_count', 0)} fields and {merge_result.get('choices_copied_count', 0)} choices.",
                        "new_form_path": output_path,
                    },
                    indent=2,
                )

            except Exception as e:
                import traceback

                traceback.print_exc()
                return json.dumps({"success": False, "error": str(e)})
            finally:
                db.close()

        @tool
        def plan_and_execute_edits(user_prompt: str) -> str:
            """
            Use this tool for any request to edit the current form, such as adding, deleting, or modifying questions, choices, or settings.
            Pass the user's entire, original prompt to this tool.
            """
            try:
                task_manager = create_task_manager(self.xml_file_path)
                # The new task_manager uses its own LLM to create the session
                session = task_manager.create_task_session(user_prompt)
                # We immediately execute the plan that was just created
                result = task_manager.execute_task_session(session_id=session["session_id"], confirm=True)
                return json.dumps(result, indent=2)
            except Exception as e:
                return json.dumps(
                    {"success": False, "error": f"An error occurred during planning and execution: {str(e)}"}
                )

        return [
            plan_and_execute_edits,
            clone_form_with_filter,
            merge_forms_from_db,
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
            system_prompt = SystemMessage("""You are an expert XLSForm agent. Your primary job is to analyze a user's intent and route their request to the correct high-level tool.

                Here are the available workflows:

                **Workflow 1: Creating a New, Filtered Form**
                - **If** the user's request is to 'clone', 'filter', or 'create a new form' based on specific sections or equipment types...
                - **Then** you MUST call the `clone_form_with_filter` tool.
                - You must extract the `new_form_name` and the `equipment_list_csv` from the user's prompt.

                **Workflow 2: Merging Forms**
                - **If** the user's request is to 'merge', 'copy questions from', or 'add fields from' another form in the database...
                - **Then** you MUST call the `merge_forms_from_db` tool.
                - You must extract the `source_form_name`, `destination_form_name`, and `field_names_csv`.

                **Workflow 3: Editing the Current Form**
                - **For ANY other request** to edit the current form (such as adding, deleting, or modifying questions, choices, or settings)...
                - **Then** you MUST call the `plan_and_execute_edits` tool.
                - You MUST pass the user's entire, original prompt to this tool.

                These are the only three workflows available. Choose the single best tool for the user's request.
                """)
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


def create_proper_xlsform_agent(xml_file_path: str, base_original_path: str = None):
    """Factory function to create the proper XLSForm agent"""
    return XLSFormProperAgent(xml_file_path, base_original_path=base_original_path)
