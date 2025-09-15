import json
import os
import shutil
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import FormVersion, User
from form_exporter import FormExporter
from form_ingestor import FormIngestor
from langgraph_proper_agent import create_proper_xlsform_agent
from models import (
    Choice,
    ChoiceCreate,
    ChoiceList,
    ChoiceUpdate,
    FieldTypeInfo,
    FormSettings,
    FormSettingsUpdate,
    PaginationParams,
    SurveyField,
    SurveyFieldCreate,
    SurveyFieldResponse,
    SurveyFieldUpdate,
    SurveyStats,
    XLSFormData,
    XLSFormStats,
)
from xml_parser import XLSFormParser

app = FastAPI(
    title="XLSForm AI Editor API",
    description="AI-powered XLSForm editing with natural language prompts",
    version="2.0.0",
)

# Global storage for current form
current_form_analysis: Optional[Dict[str, Any]] = None
current_uploaded_file: Optional[str] = None
current_modified_file: Optional[str] = None
edit_history: List[Dict[str, Any]] = []

# =============== CORE API ENDPOINTS ===============


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Upload and PARSE an XML file, ingesting it into the relational database.
    This replaces the old in-memory analysis.
    """

    if not file.filename.lower().endswith((".xml", ".xls")):
        raise HTTPException(status_code=400, detail="Only XML and XLS files are supported")

    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, file.filename)

    try:
        content = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(content)

        # TODO: Get the authenticated user. For now, we'll fetch a placeholder admin user (ID=1).
        # In a real app, this would come from your auth dependency.
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            # TODO:This is a fallback if no user 1 exists. In prod, you'd raise an auth error.
            user = User(username="system_admin", email="admin@system.com", password_hash="dummy")
            print("Warning: No user found. Using dummy user for ingest.")

        ingestor = FormIngestor(db, temp_file_path, user)
        new_form_version = ingestor.ingest_form()

        return {
            "success": True,
            "message": "File ingested and stored in database successfully.",
            "form_title": new_form_version.form.title,
            "new_version_id": new_form_version.id,
            "version_string": new_form_version.version_string,
            "total_fields_ingested": len(new_form_version.fields),
            "total_choices_ingested": len(new_form_version.choices),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing form: {str(e)}")

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


@app.post("/api/ai-edit")
async def ai_edit_endpoint(prompt: str, target_sheet: Optional[str] = None):
    """
    AI-powered editing with natural language prompts

    Examples:
    - "Add choices A, B, C to list MYLIST"
    - "Add row with data X, Y, Z to settings sheet"
    - "Remove all fields containing 'test' from survey sheet"

    The AI will:
    1. Parse your prompt into specific tasks
    2. Execute changes on the XML file
    3. Save a modified version with timestamp
    4. Return success/failure status
    """
    global current_uploaded_file

    if not current_uploaded_file:
        raise HTTPException(status_code=400, detail="No form uploaded. Please upload an XML file first.")

    try:
        # Create LangGraph ReAct Agent
        agent = create_proper_xlsform_agent(current_uploaded_file)

        # Add target sheet context to prompt if specified
        enhanced_prompt = prompt
        if target_sheet:
            enhanced_prompt = f"Focus on the '{target_sheet}' sheet. {prompt}"

        # Process the prompt using the ReAct agent
        result = await agent.process_prompt(enhanced_prompt)

        if result["success"]:
            # Check for modified file
            modified_file_created = False
            global current_modified_file, edit_history

            if current_uploaded_file:
                import glob

                original_name = os.path.basename(current_uploaded_file).replace(".xml", "")
                pattern = f"modified_{original_name}_*.xml"
                modified_files = glob.glob(pattern)

                if modified_files:
                    current_modified_file = max(modified_files, key=os.path.getctime)
                    modified_file_created = True

            # Check for success indicators
            success_indicators = [
                "successfully added",
                "added choice option",
                "modified_file_path",
                "_modified.xml",
                "backup_created",
            ]

            response_lower = result["agent_response"].lower()
            actual_success = any(indicator.lower() in response_lower for indicator in success_indicators)

            # Require tool calls and modified file for success
            tool_calls_made = int(result.get("tool_calls_made", 0) or 0)
            if tool_calls_made == 0 or not modified_file_created:
                raise HTTPException(status_code=422, detail="AI did not execute tools or no modified file was produced")

            # Add to edit history
            edit_history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "prompt": prompt,
                    "target_sheet": target_sheet,
                    "success": modified_file_created or actual_success,
                    "changes_applied": modified_file_created,
                }
            )

            return {
                "success": True,
                "prompt": prompt,
                "target_sheet": target_sheet,
                "agent_response": result["agent_response"],
                "tool_calls_made": tool_calls_made,
                "summary": "Changes applied successfully",
                "modified_file": current_modified_file,
                "changes_applied": True,
            }
        else:
            return {"success": False, "error": result["error"], "prompt": prompt, "target_sheet": target_sheet}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI editing error: {str(e)}")


@app.get("/api/export/xml")
async def export_xml(version_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Generates and downloads a valid XML form file from the database
    based on the provided form_version_id.
    """

    # The 'fields' and 'choices' will be auto-loaded via the SQLAlchemy relationships
    version_obj = db.query(FormVersion).filter(FormVersion.id == version_id).first()

    if version_obj is None:
        raise HTTPException(status_code=404, detail="A form version with this ID was not found.")

    try:
        exporter = FormExporter(version_obj)
        temp_file_path = exporter.build_xml()

        export_filename = f"{version_obj.form.form_id_string}_{version_obj.version_string}.xml"

        background_tasks.add_task(os.remove, temp_file_path)

        return FileResponse(
            path=temp_file_path,
            media_type="application/xml",
            filename=export_filename,
            headers={"Content-Disposition": f"attachment; filename={export_filename}"},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting XML: {str(e)}")


@app.get("/api/status")
async def get_status():
    """
    Get current system status

    Shows what file is loaded, if there are modifications, and edit history
    """
    global edit_history, current_uploaded_file, current_modified_file, current_form_analysis

    return {
        "has_file_uploaded": current_uploaded_file is not None,
        "original_file": current_uploaded_file,
        "modified_file": current_modified_file,
        "has_modifications": current_modified_file is not None,
        "worksheets": list(current_form_analysis.get("worksheets", {}).keys()) if current_form_analysis else [],
        "total_edits": len(edit_history),
        "edit_history": edit_history[-5:],  # Last 5 edits
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
