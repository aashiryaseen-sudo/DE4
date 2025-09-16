"""
Dynamic Task Management System for XLSForm Edits
Runtime-named tasks with a registry of handlers (Cursor-like TODOs)
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

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
    action: str  # free-form, e.g., "add_row", "add_choice_batch"
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
    status: str = "pending"  # pending, executing, completed, partial_success, failed
    created_at: str = None
    completed_at: str = None
    modified_files: List[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.modified_files is None:
            self.modified_files = []


TASK_SESSIONS_CACHE: Dict[str, Any] = {}


class XLSFormTaskManager:
    """Manages complex XLSForm editing with runtime-discovered tasks."""

    def __init__(self, xml_file_path: str):
        self.xml_file_path = xml_file_path
        self.current_session: Optional[TaskSession] = None
        self.sessions_history: List[TaskSession] = []
        # action registry → handler
        self.registry: Dict[str, Callable[[Dict[str, Any], XLSFormXMLEditor], Dict[str, Any]]] = {
            "add_row": self._handle_add_row,
            "add_choice_batch": self._handle_add_choice_batch,
            "add_choice_single": self._handle_add_choice_single,
            "analyze_structure": self._handle_analyze_structure,
            "delete_field": self._handle_delete_field,
            "modify_field_property": self._handle_modify_field_property,
            "modify_choice": self._handle_modify_choice,
        }

    # ---------- Planning ----------
    def parse_user_prompt(self, prompt: str) -> TaskSession:
        session_id = str(uuid.uuid4())[:8]
        tasks: List[DynTask] = []

        # Multi-step split by ';' or ' and '
        segments = re.split(r"[;]|\band\b", prompt, flags=re.IGNORECASE)
        for seg in segments:
            s = seg.strip()
            if not s:
                continue

            if "list" in s.lower() and "choice name" in s.lower() and "change" in s.lower():
                list_name = self._extract(r"in the ['\"]([\w:]+)['\"]\s+list", s)
                choice_name = self._extract(r"choice\s+name(?:d)?\s+['\"]([\w:]+)['\"]", s)
                prop_name = self._extract(r"change the ['\"]([\w:]+)['\"]", s)
                new_value = self._extract(r"to ['\"]([^']+)['\"]", s)

                if all([list_name, choice_name, prop_name, new_value is not None]):
                    title = f"Modify choice '{choice_name}' in list '{list_name}'"
                    params = {
                        "list_name": list_name,
                        "choice_name": choice_name,
                        "property_to_change": prop_name,
                        "new_value": new_value,
                    }
                    tasks.append(
                        DynTask(
                            id=self._tid(len(tasks)),
                            title=title,
                            action="modify_choice",
                            worksheet=None,
                            parameters=params,
                        )
                    )
                    continue

            if ("update" in s.lower() or "modify" in s.lower() or "change" in s.lower()) and "field" in s.lower():
                prop_name = self._extract(r"['\"]([\w:]+)['\"]\s+property", s)
                field_name = self._extract(r"field\s+['\"]([\w:]+)['\"]", s)
                new_value = self._extract(r"to\s+['\"]([^']+)['\"]", s)

                if prop_name and field_name and new_value is not None:
                    title = f"Modify property '{prop_name}' for field '{field_name}'"
                    params = {"field_name": field_name, "property_name": prop_name, "new_value": new_value}
                    tasks.append(
                        DynTask(
                            id=self._tid(len(tasks)),
                            title=title,
                            action="modify_field_property",
                            worksheet="survey",
                            parameters=params,
                        )
                    )
                    continue

            if ("delete" in s.lower() or "remove" in s.lower()) and "field" in s.lower():
                field_name = self._extract(r"(?:delete|remove)\s+(?:the\s+)?field\s+['\"]?([\w\-]+)['\"]?", s)
                if field_name:
                    title = f"Delete field '{field_name}' from survey"
                    tasks.append(
                        DynTask(
                            id=self._tid(len(tasks)),
                            title=title,
                            action="delete_field",
                            worksheet="survey",
                            parameters={"field_name": field_name},
                        )
                    )
                    continue

            # add row with data: v1,v2,... [in/to <sheet> sheet]
            if "add" in s.lower() and "row" in s.lower() and "data" in s.lower():
                sheet_hint = "auto_detect"
                if "to survey" in s.lower() or "in survey" in s.lower():
                    sheet_hint = "survey"
                elif "to settings" in s.lower() or "in settings" in s.lower():
                    sheet_hint = "settings"

                data_str = self._extract(r"data:\s*(.+)$", s)
                data = [d.strip() for d in data_str.split(",")] if data_str else []
                title = f"Add row with {len(data)} values to {sheet_hint}"
                tasks.append(
                    DynTask(
                        id=self._tid(len(tasks)),
                        title=title,
                        action="add_row",
                        worksheet=sheet_hint,
                        parameters={"values": data, "target_sheet": sheet_hint},
                    )
                )
                continue
            # add choices/options X,Y,Z to list NAME
            if re.search(r"add\s+(choices?|options?)", s, re.IGNORECASE) and "list" in s.lower():
                list_name = self._extract(r"(?:to|in)\s+list\s+['\"]?([\w\-]+)['\"]?", s) or "default_list"
                items_str = self._extract(r"add\s+(?:choices?|options?)\s+(.*?)\s+(?:to|in)\s+list", s)

                if items_str:
                    items = [item.strip() for item in items_str.strip(" '\"").split(",") if item.strip()]

                    if len(items) > 1:
                        title = f"Add {len(items)} choices to list {list_name}"
                        tasks.append(
                            DynTask(
                                id=self._tid(len(tasks)),
                                title=title,
                                action="add_choice_batch",
                                worksheet="auto_detect",
                                parameters={"list_name": list_name, "items": items},
                            )
                        )
                    elif items:
                        title = f"Add choice '{items[0]}' to list {list_name}"
                        tasks.append(
                            DynTask(
                                id=self._tid(len(tasks)),
                                title=title,
                                action="add_choice_single",
                                worksheet="auto_detect",
                                parameters={"list_name": list_name, "label": items[0], "name": items[0]},
                            )
                        )
                    continue

        if not tasks:
            tasks.append(
                DynTask(
                    id=self._tid(0),
                    title="Analyze form structure",
                    action="analyze_structure",
                    worksheet="all",
                    parameters={"prompt": prompt},
                )
            )

        return TaskSession(id=session_id, user_prompt=prompt, tasks=tasks)

    def create_task_session(self, user_prompt: str) -> Dict[str, Any]:
        session = self.parse_user_prompt(user_prompt)
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
            "estimated_time": f"~{max(1, len(session.tasks)) * 2}-{max(1, len(session.tasks)) * 5} seconds",
            "preview": True,
        }

    # ---------- Execution ----------
    def execute_task_session(self, session_id: str, confirm: bool = True) -> Dict[str, Any]:
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
                    if res.get("modified_file_path"):
                        session.modified_files.append(res["modified_file_path"])
                else:
                    task.status = TaskStatus.FAILED
                    task.error_message = res.get("error") or res.get("reason") or "Unknown error"
                    failed.append(task)
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                failed.append(task)

            task.completed_at = datetime.now().isoformat()
            results.append({"task_id": task.id, "title": task.title, "status": task.status, "result": task.result})

        final_output_path = None
        if editor.modified and not failed:
            final_output_path = editor.save_modified_xml()
            session.modified_files.append(final_output_path)
        elif failed:
            print(f"Session {session_id} failed. No file will be saved.")
        else:
            print(f"Session {session_id} completed, but no modifications were made. No file saved.")
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

    # ---------- Handlers (registry) ----------
    def _handle_add_row(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        result = editor.add_row_to_best_match(params.get("values", []), sheet_hint=params.get("target_sheet"))

        return result

    def _handle_add_choice_batch(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        items = [{"label": it, "name": it} for it in params.get("items", [])]
        res = editor.add_choice_options_batch(params.get("list_name", "default_list"), items, params.get("worksheet"))
        if res.get("modified") and editor.modified:
            res["success"] = True
        return res

    def _handle_add_choice_single(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        ok = editor.add_choice_option(
            params.get("list_name", "default_list"),
            params.get("label", ""),
            params.get("name", ""),
            params.get("worksheet"),
        )
        result = {"success": ok}

        return result

    def _handle_analyze_structure(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        from xml_parser import XLSFormParser

        parser = XLSFormParser(self.xml_file_path)
        analysis = parser.analyze_complete_form()
        return {"success": True, "analysis": analysis, "worksheets": list(analysis.keys())}

    def _handle_delete_field(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        field_name = params.get("field_name")
        if not field_name:
            return {"success": False, "error": "field_name parameter is missing"}

        success = editor.remove_field_by_name(field_name)
        result = {"success": success}
        if success:
            result["message"] = f"Field '{field_name}' and its choices were successfully deleted."
        elif not success:
            result["message"] = f"Could not delete field '{field_name}'. It may not exist."

        return result

    def _handle_modify_field_property(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        field_name = params.get("field_name")
        prop_name = params.get("property_name")
        new_value = params.get("new_value")

        if not all([field_name, prop_name, new_value is not None]):
            return {
                "success": False,
                "error": "Missing one of required parameters: field_name, property_name, new_value",
            }

        success = editor.modify_field_property(field_name, prop_name, new_value)
        result = {"success": success}
        if success and editor.modified:
            result["message"] = f"Property '{prop_name}' for field '{field_name}' was updated."
        elif not success:
            result["message"] = f"Could not modify property for field '{field_name}'."

        return result

    def _handle_modify_choice(self, params: Dict[str, Any], editor: XLSFormXMLEditor) -> Dict[str, Any]:
        list_name = params.get("list_name")
        choice_name = params.get("choice_name")
        prop_name = params.get("property_to_change")
        new_value = params.get("new_value")

        if not all([list_name, choice_name, prop_name, new_value is not None]):
            return {"success": False, "error": "Missing one of required parameters for modify_choice"}

        success = editor.modify_choice_property(list_name, choice_name, prop_name, new_value)
        result = {"success": success}

        if success and editor.modified:
            result["message"] = f"Choice '{choice_name}' in list '{list_name}' was updated."
        elif not success:
            result["message"] = f"Could not modify choice '{choice_name}'."

        return result

    # ---------- Helpers ----------
    def _extract(self, pattern: str, text: str) -> Optional[str]:
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _extract_csv_after_colon(self, key: str, text: str) -> List[str]:
        m = re.search(rf"{key}\s*:\s*([^\n]+)", text, re.IGNORECASE)
        return [v.strip() for v in m.group(1).split(",")] if m else []

    def _extract_csv_after_word(self, word: str, text: str) -> List[str]:
        # after the word, capture a csv sequence
        m = re.search(rf"{word}\s+([^\n]+)", text, re.IGNORECASE)
        return [v.strip() for v in m.group(1).split(",")] if m else []

    def _tid(self, idx: int) -> str:
        return f"task_{idx + 1}"

    # External status helpers
    def get_session_status(self, session_id: str = None) -> Dict[str, Any]:
        session = self.current_session
        if session_id:
            session = next((s for s in self.sessions_history if s.id == session_id), None)
        if not session:
            return {"error": "Session not found"}
        return {
            "session_id": session.id,
            "user_prompt": session.user_prompt,
            "status": session.status,
            "total_tasks": len(session.tasks),
            "task_breakdown": [
                {
                    "id": t.id,
                    "title": t.title,
                    "action": t.action,
                    "worksheet": t.worksheet,
                    "status": t.status,
                    "started_at": t.started_at,
                    "completed_at": t.completed_at,
                }
                for t in session.tasks
            ],
            "modified_files": session.modified_files,
            "created_at": session.created_at,
            "completed_at": session.completed_at,
        }

    def rollback_session(self, session_id: str) -> Dict[str, Any]:
        return {"message": f"Rollback for session {session_id} would restore from backup", "implementation": "TODO"}


def create_task_manager(xml_file_path: str) -> XLSFormTaskManager:
    return XLSFormTaskManager(xml_file_path)
