"""
Dynamic Task Management System for XLSForm Edits
Runtime-named tasks with a registry of handlers (Cursor-like TODOs)
"""

import json
import uuid
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass


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


class XLSFormTaskManager:
    """Manages complex XLSForm editing with runtime-discovered tasks."""

    def __init__(self, xml_file_path: str):
        self.xml_file_path = xml_file_path
        self.current_session: Optional[TaskSession] = None
        self.sessions_history: List[TaskSession] = []
        # action registry → handler
        self.registry: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "add_row": self._handle_add_row,
            "add_choice_batch": self._handle_add_choice_batch,
            "add_choice_single": self._handle_add_choice_single,
            "analyze_structure": self._handle_analyze_structure,
        }

    # ---------- Planning ----------
    def parse_user_prompt(self, prompt: str) -> TaskSession:
        session_id = str(uuid.uuid4())[:8]
        tasks: List[DynTask] = []
        lower = prompt.lower()

        # Multi-step split by ';' or ' and '
        segments = re.split(r"[;]|\band\b", prompt, flags=re.IGNORECASE)
        for seg in segments:
            s = seg.strip()
            if not s:
                continue
            # add row with data: v1,v2,... [in/to <sheet> sheet]
            if "add" in s.lower() and "row" in s.lower() and "data" in s.lower():
                sheet = self._extract(r"(?:in|to)\s+([\w\- ]+)\s+sheet", s) or "auto_detect"
                data = self._extract_csv_after_colon("data", s)
                title = f"Add row with {len(data)} values to {sheet}"
                tasks.append(DynTask(id=self._tid(len(tasks)), title=title, action="add_row", worksheet=sheet, parameters={"values": data, "target_sheet": sheet}))
                continue
            # add choices/options X,Y,Z to list NAME
            if re.search(r"add\s+(choices?|options?)", s, re.IGNORECASE):
                items = self._extract_csv_after_word("add", s)
                list_name = self._extract(r"(?:to|in)\s+list\s+([\w\-]+)", s) or "default_list"
                if len(items) > 1:
                    title = f"Add {len(items)} choices to list {list_name}"
                    tasks.append(DynTask(id=self._tid(len(tasks)), title=title, action="add_choice_batch", worksheet="auto_detect", parameters={"list_name": list_name, "items": items}))
                elif items:
                    title = f"Add choice '{items[0]}' to list {list_name}"
                    tasks.append(DynTask(id=self._tid(len(tasks)), title=title, action="add_choice_single", worksheet="auto_detect", parameters={"list_name": list_name, "label": items[0], "name": items[0]}))

        if not tasks:
            tasks.append(DynTask(id=self._tid(0), title="Analyze form structure", action="analyze_structure", worksheet="all", parameters={"prompt": prompt}))

        return TaskSession(id=session_id, user_prompt=prompt, tasks=tasks)

    def create_task_session(self, user_prompt: str) -> Dict[str, Any]:
        session = self.parse_user_prompt(user_prompt)
        self.current_session = session
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
    def execute_task_session(self, confirm: bool = True) -> Dict[str, Any]:
        if not self.current_session:
            return {"error": "No active task session"}
        if not confirm:
            return {"message": "Task execution cancelled"}

        session = self.current_session
        session.status = "executing"
        results: List[Dict[str, Any]] = []
        failed = []

        for task in session.tasks:
            handler = self.registry.get(task.action)
            task.started_at = datetime.now().isoformat()
            task.status = TaskStatus.IN_PROGRESS

            if not handler:
                task.status = TaskStatus.FAILED
                task.error_message = f"Unsupported action: {task.action}"
                task.completed_at = datetime.now().isoformat()
                results.append({"task_id": task.id, "title": task.title, "status": task.status, "error": task.error_message})
                failed.append(task)
                continue

            try:
                res = handler(task.parameters)
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

        session.status = "partial_success" if failed and any(t.status == TaskStatus.COMPLETED for t in session.tasks) else ("failed" if failed else "completed")
        session.completed_at = datetime.now().isoformat()
        self.sessions_history.append(session)

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
    def _handle_add_row(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from xml_editor import create_xml_editor
        editor = create_xml_editor(self.xml_file_path)
        result = editor.add_row_to_best_match(params.get("values", []), sheet_hint=params.get("target_sheet"))
        if result.get("success") and editor.modified:
            out = editor.save_modified_xml()
            result["modified_file_path"] = out
        return result

    def _handle_add_choice_batch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from xml_editor import create_xml_editor
        editor = create_xml_editor(self.xml_file_path)
        items = [{"label": it, "name": it} for it in params.get("items", [])]
        res = editor.add_choice_options_batch(params.get("list_name", "default_list"), items, params.get("worksheet"))
        if res.get("modified") and editor.modified:
            out = editor.save_modified_xml()
            res["modified_file_path"] = out
            res["success"] = True
        return res

    def _handle_add_choice_single(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from xml_editor import create_xml_editor
        editor = create_xml_editor(self.xml_file_path)
        ok = editor.add_choice_option(params.get("list_name", "default_list"), params.get("label", ""), params.get("name", ""), params.get("worksheet"))
        result = {"success": ok}
        if ok and editor.modified:
            out = editor.save_modified_xml()
            result["modified_file_path"] = out
        return result

    def _handle_analyze_structure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from xml_parser import XLSFormParser
        parser = XLSFormParser(self.xml_file_path)
        analysis = parser.analyze_all_worksheets()
        return {"success": True, "analysis": analysis, "worksheets": list(analysis.keys())}

    # ---------- Helpers ----------
    def _extract(self, pattern: str, text: str) -> Optional[str]:
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _extract_csv_after_colon(self, key: str, text: str) -> List[str]:
        m = re.search(rf"{key}\s*:\s*([^\n]+)", text, re.IGNORECASE)
        return [v.strip() for v in m.group(1).split(',')] if m else []

    def _extract_csv_after_word(self, word: str, text: str) -> List[str]:
        # after the word, capture a csv sequence
        m = re.search(rf"{word}\s+([^\n]+)", text, re.IGNORECASE)
        return [v.strip() for v in m.group(1).split(',')] if m else []

    def _tid(self, idx: int) -> str:
        return f"task_{idx+1}"

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
                } for t in session.tasks
            ],
            "modified_files": session.modified_files,
            "created_at": session.created_at,
            "completed_at": session.completed_at,
        }

    def rollback_session(self, session_id: str) -> Dict[str, Any]:
        return {"message": f"Rollback for session {session_id} would restore from backup", "implementation": "TODO"}


def create_task_manager(xml_file_path: str) -> XLSFormTaskManager:
    return XLSFormTaskManager(xml_file_path)
