from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
import json
import os
import tempfile
from datetime import datetime
from typing import List, Optional, Dict, Any
from models import (
    SurveyField, SurveyFieldCreate, SurveyFieldUpdate, 
    SurveyFieldResponse, PaginationParams, SurveyStats, FieldTypeInfo,
    Choice, ChoiceCreate, ChoiceUpdate, ChoiceList,
    FormSettings, FormSettingsUpdate, XLSFormData, XLSFormStats
)
from xml_parser import XLSFormParser
from langgraph_proper_agent import create_proper_xlsform_agent

app = FastAPI(
    title="XLSForm AI Editor API",
    description="AI-powered XLSForm editing with natural language prompts",
    version="2.0.0"
)

# Global storage for current form
current_form_analysis: Optional[Dict[str, Any]] = None
current_uploaded_file: Optional[str] = None
current_modified_file: Optional[str] = None
edit_history: List[Dict[str, Any]] = []

# =============== CORE API ENDPOINTS ===============

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload and analyze XML file
    
    This endpoint:
    1. Accepts XML/XLS file upload
    2. Analyzes all worksheets automatically
    3. Stores analysis for AI editing
    """
    global current_form_analysis, current_uploaded_file
    
    if not file.filename.lower().endswith(('.xml', '.xls')):
        raise HTTPException(status_code=400, detail="Only XML and XLS files are supported")
    
    # Save uploaded file
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    try:
        # Analyze the uploaded file
        parser = XLSFormParser(file_path)
        current_form_analysis = parser.analyze_complete_form()
        current_uploaded_file = file_path
        
        return {
            "success": True,
            "message": "File uploaded and analyzed successfully",
            "file_path": file_path,
            "worksheets": list(current_form_analysis.get('worksheets', {}).keys()),
            "total_sheets": len(current_form_analysis.get('worksheets', {})),
            "analysis": current_form_analysis
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing uploaded form: {str(e)}")

@app.post("/api/ai-edit")
async def ai_edit_endpoint(
    prompt: str,
    target_sheet: Optional[str] = None
):
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
                original_name = os.path.basename(current_uploaded_file).replace('.xml', '')
                pattern = f"modified_{original_name}_*.xml"
                modified_files = glob.glob(pattern)
                
                if modified_files:
                    current_modified_file = max(modified_files, key=os.path.getctime)
                    modified_file_created = True
            
            # Check for success indicators
            success_indicators = [
                "successfully added", "added choice option", 
                "modified_file_path", "_modified.xml", "backup_created"
            ]
            
            response_lower = result["agent_response"].lower()
            actual_success = any(indicator.lower() in response_lower for indicator in success_indicators)
            
            # Require tool calls and modified file for success
            tool_calls_made = int(result.get("tool_calls_made", 0) or 0)
            if tool_calls_made == 0 or not modified_file_created:
                raise HTTPException(
                    status_code=422,
                    detail="AI did not execute tools or no modified file was produced"
                )
            
            # Add to edit history
            edit_history.append({
                'timestamp': datetime.now().isoformat(),
                'prompt': prompt,
                'target_sheet': target_sheet,
                'success': modified_file_created or actual_success,
                'changes_applied': modified_file_created
            })
            
            return {
                'success': True,
                'prompt': prompt,
                'target_sheet': target_sheet,
                'agent_response': result["agent_response"],
                'tool_calls_made': tool_calls_made,
                'summary': "Changes applied successfully",
                'modified_file': current_modified_file,
                'changes_applied': True
            }
        else:
            return {
                'success': False,
                'error': result["error"],
                'prompt': prompt,
                'target_sheet': target_sheet
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI editing error: {str(e)}")

@app.get("/api/export/xml")
async def export_xml():
    """
    Download the modified XML file
    
    Returns the latest modified version if available, otherwise the original file
    """
    global current_uploaded_file, current_modified_file
    
    if not current_uploaded_file:
        raise HTTPException(status_code=400, detail="No form uploaded. Please upload an XML file first.")
    
    try:
        # Prefer modified file if available, otherwise return original
        export_file_path = current_modified_file if current_modified_file and os.path.exists(current_modified_file) else current_uploaded_file
        
        if not os.path.exists(export_file_path):
            raise HTTPException(status_code=404, detail="XML file not found")
        
        filename = os.path.basename(current_uploaded_file)
        
        # Determine filename based on whether we're exporting modified or original
        if export_file_path == current_modified_file:
            export_filename = f"edited_{filename}"
            file_type = "modified"
        else:
            export_filename = f"original_{filename}"
            file_type = "original"
        
        return FileResponse(
            export_file_path,
            media_type='application/xml',
            filename=export_filename,
            headers={
                "Content-Disposition": f"attachment; filename={export_filename}",
                "X-File-Type": file_type,
                "X-Has-Modifications": str(current_modified_file is not None).lower()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export error: {str(e)}")

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
        "worksheets": list(current_form_analysis.get('worksheets', {}).keys()) if current_form_analysis else [],
        "total_edits": len(edit_history),
        "edit_history": edit_history[-5:],  # Last 5 edits
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)