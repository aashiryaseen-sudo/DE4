"""
Dynamic Task Management System for XLSForm Edits
LLM-powered task planning based on user prompts.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from xml_editor import XLSFormXMLEditor, create_xml_editor


class TaskStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DynTask:
    id: str
    title: str
    action: str
    worksheet: Optional[str]
    parameters: Dict[str, Any]
    status: str = TaskStatus.PENDING
    created_at: str = None
    started_at: str = None
    completed_at: str = None
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


@dataclass
class TaskSession:
    id: str
    user_prompt: str
    tasks: List[DynTask]
    status: str = "pending"
    created_at: str = None
    completed_at: str = None
    modified_files: List[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.modified_files is None:
            self.modified_files = []


class DeleteFieldParams(BaseModel):
    """Parameters for deleting a field (question) from the survey sheet."""

    field_name: str = Field(..., description="The exact 'name' of the field to delete.")


class AddChoiceBatchParams(BaseModel):
    """Parameters for adding multiple new choices to a dropdown list."""

    list_name: str = Field(..., description="The name of the choice list to add options to.")
    items: List[str] = Field(..., description="A list of the new choice labels to add.")
    worksheet: Optional[str] = Field(
        "choices", description="The name of the worksheet containing choice lists, typically 'choices'."
    )


class ModifyFieldPropertyParams(BaseModel):
    """Parameters to modify a property of a field or a form setting."""

    worksheet_name: str = Field(
        ..., description="The name of the worksheet, e.g., 'survey' for questions or 'settings' for form settings."
    )
    key_field_name: str = Field(
        ..., description="The name of the column used to find the correct row, e.g., 'name' for the survey sheet."
    )
    key_field_value: str = Field(
        ..., description="The value to look for in the key_field_name column to identify the row."
    )
    property_to_change: str = Field(..., description="The name of the column (property) to modify.")
    new_value: str = Field(..., description="The new value to set for the property.")


class ModifyChoiceParams(BaseModel):
    """Parameters to modify a property of an existing choice in a list."""

    list_name: str = Field(..., description="The name of the choice list containing the choice to modify.")
    choice_name: str = Field(..., description="The 'name' of the specific choice to modify.")
    property_to_change: str = Field(..., description="The property of the choice to change, e.g., 'label'.")
    new_value: str = Field(..., description="The new value for the property.")


class AddRowParams(BaseModel):
    """Parameters to add a new row of data to a worksheet."""

    values: List[str] = Field(..., description="A list of strings representing the cell values for the new row.")
    target_sheet: Optional[str] = Field(
        "survey", description="The recommended worksheet to add the row to, e.g., 'survey'."
    )


class Operator(str, Enum):
    """Enumeration for filter operators."""

    equals = "equals"
    contains = "contains"
    starts_with = "starts_with"
    ends_with = "ends_with"


class FieldFilter(BaseModel):
    """A single filter condition to apply to a field."""

    property: str = Field(..., description="The property/column to check, e.g., 'type', 'name', 'label'.")
    operator: Operator = Field(..., description="The comparison operator to use.")
    value: str = Field(..., description="The value to compare against.")


class DeleteByFilterParams(BaseModel):
    """
    Defines a request to delete fields that match a set of filter groups.
    The outer list is joined by OR, the inner list is joined by AND.
    Example: [[A, B], [C]] means (A AND B) OR C.
    """

    filter_groups: List[List[FieldFilter]] = Field(..., description="A list of filter groups (lists) to apply.")


TASK_SESSIONS_CACHE: Dict[str, Any] = {}


class XLSFormTaskManager:
    """Manages complex XLSForm editing with an LLM-powered task planner."""

    def __init__(self, xml_file_path: str):
        self.xml_file_path = xml_file_path
        self.current_session: Optional[TaskSession] = None
        self.sessions_history: List[TaskSession] = []

        # Initialize the LLM for parsing. It's bound with the "tools" it can use.
        self.parser_llm = ChatOpenAI(model="gpt-4.1", temperature=0).bind_tools(self._get_available_actions())

        # The registry of handlers remains the same.
        self.registry: Dict[str, Callable[[Dict[str, Any], XLSFormXMLEditor], Dict[str, Any]]] = {
            "delete_field": self._handle_delete_field,
            "add_choice_batch": self._handle_add_choice_batch,
            "modify_field_property": self._handle_modify_field_property,
            "modify_choice": self._handle_modify_choice,
            "add_row": self._handle_add_row,
            "delete_by_filter": self._handle_delete_by_filter,
        }

    def _get_available_actions(self) -> List:
        """Returns the list of Pydantic models that define the LLM's tools."""
        return [
            DeleteByFilterParams,
            DeleteFieldParams,
            AddChoiceBatchParams,
            ModifyFieldPropertyParams,
            ModifyChoiceParams,
            AddRowParams,
        ]

    # ---------- Planning (Now LLM-Powered) ----------
    def _parse_prompt_with_llm(self, prompt: str) -> List[DynTask]:
        """Uses an LLM with tool-calling to parse the prompt into a list of tasks."""
        system_prompt = """
          You are an expert XLSForm task planner. Your job is to analyze a user's request and convert it into a precise, 
          structured list of one or more function calls required to fulfill the request.

        **IMPORTANT**: For complex conditional deletions (e.g., "delete all fields where type is image and name ends with 'Photo'"), 
        you MUST use the `DeleteByFilterParams` tool. You must construct the filter groups to match the user's logic.

        - A request like "(condition A AND condition B) OR (condition C)" should be structured as: `filter_groups=[[A, B], [C]]`.
        - A request like "condition A AND condition B" should be structured as: `filter_groups=[[A, B]]`.

        For simple requests (e.g., "delete the field 'age'"), you can still use the simpler `DeleteFieldParams` tool.

        Key instructions for other tools:
        - A user's request to change a "question" or "field" refers to the 'survey' sheet. For `ModifyFieldPropertyParams`, 
        the `worksheet_name` is 'survey', `key_field_name` is 'name', and `key_field_value` is the question's name.
        - A "setting" refers to the 'settings' sheet.
        - When adding choices, always use `add_choice_batch`.
        """

        # Invoke the LLM with the prompt and instructions
        response = self.parser_llm.invoke([("system", system_prompt), ("human", prompt)])

        tasks: List[DynTask] = []

        # Convert the LLM's desired tool calls into our internal DynTask format
        for tool_call in response.tool_calls:
            action_name = tool_call["name"]

            # Map the Pydantic model name back to our snake_case action name
            # Example: 'DeleteFieldParams' -> 'delete_field'
            parsed_action_name = (
                "".join(["_" + i.lower() if i.isupper() else i for i in action_name]).lstrip("_").replace("_params", "")
            )

            if parsed_action_name in self.registry:
                task = DynTask(
                    id=self._tid(len(tasks)),
                    title=f"Perform action: {parsed_action_name}",  # Title can be improved
                    action=parsed_action_name,
                    worksheet=tool_call["args"].get("worksheet_name") or tool_call["args"].get("target_sheet"),
                    parameters=tool_call["args"],
                )
                tasks.append(task)

        return tasks

    def create_task_session(self, user_prompt: str) -> Dict[str, Any]:
        """Creates a new task session by parsing the user prompt with the LLM."""
        session_id = str(uuid.uuid4())[:8]

        # Use the new LLM parser
        tasks = self._parse_prompt_with_llm(user_prompt)

        session = TaskSession(id=session_id, user_prompt=user_prompt, tasks=tasks)
        self.current_session = session
        TASK_SESSIONS_CACHE[session.id] = session

        return {
            "session_id": session.id,
            "user_prompt": session.user_prompt,
            "total_tasks": len(session.tasks),
            "tasks": [
                {"id": t.id, "title": t.title, "action": t.action, "worksheet": t.worksheet, "status": t.status}
                for t in session.tasks
            ],
            "estimated_time": f"~{max(1, len(session.tasks)) * 3}-{max(1, len(session.tasks)) * 6} seconds",  # Increased estimate for LLM latency
            "preview": True,
        }

    # ---------- Execution (No Changes Needed) ----------
    def execute_task_session(self, session_id: str, confirm: bool = True) -> Dict[str, Any]:
        # This entire method remains unchanged. It just executes the plan it's given.
        session = TASK_SESSIONS_CACHE.get(session_id)
        if session is None:
            return {"success": False, "error": f"Session ID '{session_id}' not found or has expired."}
        if not confirm:
            return {"success": False, "message": "Task execution cancelled by user."}

        session.status = "executing"
        results: List[Dict[str, Any]] = []
        failed = []
        editor = create_xml_editor(self.xml_file_path)

        for task in session.tasks:
            handler = self.registry.get(task.action)
            task.started_at = datetime.now().isoformat()
            task.status = TaskStatus.IN_PROGRESS

            if not handler:
                task.status = TaskStatus.FAILED
                task.error_message = f"Unsupported action: {task.action}"
                task.completed_at = datetime.now().isoformat()
                results.append(
                    {"task_id": task.id, "title": task.title, "status": task.status, "error": task.error_message}
                )
                failed.append(task)
                continue

            try:
                res = handler(task.parameters, editor)
                task.result = res
                if res.get("success"):
                    task.status = TaskStatus.COMPLETED
                else:
                    task.status = TaskStatus.FAILED
                    task.error_message = res.get("error") or res.get("reason") or "Unknown error"
                    failed.append(task)
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                failed.append(task)

            task.completed_at = datetime.now().isoformat()
            results.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "result": task.result,
                    "error": task.error_message,
                }
            )

        if editor.modified:
            final_output_path = editor.save_modified_xml()
            if session.modified_files is None:
                session.modified_files = []
            session.modified_files.append(final_output_path)

        session.status = (
            "partial_success"
            if failed and any(t.status == TaskStatus.COMPLETED for t in session.tasks)
            else ("failed" if failed else "completed")
        )
        session.completed_at = datetime.now().isoformat()
        self.sessions_history.append(session)
        if session.id in TASK_SESSIONS_CACHE:
            del TASK_SESSIONS_CACHE[session.id]

        return {
            "session_id": session.id,
            "status": session.status,
            "total_tasks": len(session.tasks),
            "completed_tasks": len([t for t in session.tasks if t.status == TaskStatus.COMPLETED]),
            "failed_tasks": len(failed),
            "modified_files": session.modified_files,
            "results": results,
            "execution_time": f"{(datetime.fromisoformat(session.completed_at) - datetime.fromisoformat(session.created_at)).total_seconds():.1f}s",
        }

    # ---------- Handlers (No Changes Needed) ----------
    def _handle_add_row(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        return editor.add_row_to_best_match(params.get("values", []), sheet_hint=params.get("target_sheet"))

    def _handle_add_choice_batch(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        items = [{"label": it, "name": it} for it in params.get("items", [])]
        res = editor.add_choice_options_batch(params.get("list_name", "default_list"), items, params.get("worksheet"))
        if res.get("modified") and editor.modified:
            res["success"] = True
        return res

    def _handle_modify_field_property(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        success = editor.modify_field_property(
            params["worksheet_name"],
            params["key_field_name"],
            params["key_field_value"],
            params["property_to_change"],
            params["new_value"],
        )
        return {"success": success}

    def _handle_delete_field(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        success = editor.remove_field_by_name(params["field_name"])
        return {"success": success}

    def _handle_modify_choice(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        success = editor.modify_choice_property(
            params["list_name"], params["choice_name"], params["property_to_change"], params["new_value"]
        )
        return {"success": success}

    def _handle_delete_by_filter(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        """Handler to call the new query engine in the XML editor."""
        filter_groups = params.get("filter_groups", [])
        if not filter_groups:
            return {"success": False, "error": "No filters were provided for the deletion."}

        result = editor.remove_fields_by_filter(filter_groups)
        return result

    # ---------- Helpers ----------
    def _tid(self, idx: int) -> str:
        return f"task_{idx + 1}"


def create_task_manager(xml_file_path: str) -> XLSFormTaskManager:
    return XLSFormTaskManager(xml_file_path)
