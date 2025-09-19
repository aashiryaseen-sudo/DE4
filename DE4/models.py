from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

class FieldType(str, Enum):
    """Common field types found in the survey"""
    BEGIN_GROUP = "begin group"
    END_GROUP = "end group"
    NOTE = "note"
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    SELECT_ONE = "select_one"
    SELECT_MULTIPLE = "select_multiple"
    GEOPOINT = "geopoint"
    IMAGE = "image"
    CALCULATE = "calculate"
    USERNAME = "username"
    BEGIN_REPEAT = "begin repeat"
    END_REPEAT = "end repeat"
    ACKNOWLEDGE = "acknowledge"
    START = "start"
    END = "end"

class SurveyField(BaseModel):
    """Model representing a survey field with all its properties"""
    id: Optional[int] = Field(None, description="Auto-generated ID for database")
    name: Optional[str] = Field("", description="Field name/identifier")
    type: str = Field(..., description="Field type (text, select_one, etc.)")
    label: Optional[str] = Field("", description="Human-readable label")
    appearance: Optional[str] = Field("", description="UI appearance settings")
    required: Optional[str] = Field("", description="Whether field is required (1 or empty)")
    relevant: Optional[str] = Field("", description="Relevance condition")
    hint: Optional[str] = Field("", description="Help text for the field")
    constraint: Optional[str] = Field("", description="Validation constraint")
    constraint_message: Optional[str] = Field("", description="Error message for constraint")
    calculation: Optional[str] = Field("", description="Calculation formula")
    repeat_count: Optional[str] = Field("", description="Repeat count for repeat groups")
    read_only: Optional[str] = Field("", description="Whether field is read-only")
    default: Optional[str] = Field("", description="Default value")
    image: Optional[str] = Field("", description="Image settings")
    audio: Optional[str] = Field("", description="Audio settings")
    media_audio: Optional[str] = Field("", description="Media audio settings")
    media_video: Optional[str] = Field("", description="Media video settings")
    timestamp_req: Optional[str] = Field("", description="Timestamp requirement")
    fetch_data_from_riptide: Optional[str] = Field("", description="Riptide data fetch setting")
    fetch_data_for_field_name: Optional[str] = Field("", description="Field name for data fetch")
    riptide_api_prop_name: Optional[str] = Field("", description="Riptide API property name")
    fetch_unit_tag_from_field_name: Optional[str] = Field("", description="Unit tag fetch setting")
    include_in_building_profiles: Optional[str] = Field("", description="Building profile inclusion")
    equipment_type: Optional[str] = Field("", description="Equipment type")
    equipment_code: Optional[str] = Field("", description="Equipment code")
    constraint_check: Optional[str] = Field("", description="Constraint check")
    order: Optional[str] = Field("", description="Display order")
    alias: Optional[str] = Field("", description="Field alias")

    class Config:
        json_encoders = {
            # Handle any special encoding if needed
        }

class SurveyFieldCreate(BaseModel):
    """Model for creating a new survey field"""
    name: str = Field(..., min_length=1, description="Field name/identifier")
    type: str = Field(..., min_length=1, description="Field type")
    label: Optional[str] = ""
    appearance: Optional[str] = ""
    required: Optional[str] = ""
    relevant: Optional[str] = ""
    hint: Optional[str] = ""
    constraint: Optional[str] = ""
    constraint_message: Optional[str] = ""
    calculation: Optional[str] = ""
    repeat_count: Optional[str] = ""
    read_only: Optional[str] = ""
    default: Optional[str] = ""
    image: Optional[str] = ""
    audio: Optional[str] = ""
    media_audio: Optional[str] = ""
    media_video: Optional[str] = ""
    timestamp_req: Optional[str] = ""
    fetch_data_from_riptide: Optional[str] = ""
    fetch_data_for_field_name: Optional[str] = ""
    riptide_api_prop_name: Optional[str] = ""
    fetch_unit_tag_from_field_name: Optional[str] = ""
    include_in_building_profiles: Optional[str] = ""
    equipment_type: Optional[str] = ""
    equipment_code: Optional[str] = ""
    constraint_check: Optional[str] = ""
    order: Optional[str] = ""
    alias: Optional[str] = ""

class SurveyFieldUpdate(BaseModel):
    """Model for updating an existing survey field"""
    name: Optional[str] = None
    type: Optional[str] = None
    label: Optional[str] = None
    appearance: Optional[str] = None
    required: Optional[str] = None
    relevant: Optional[str] = None
    hint: Optional[str] = None
    constraint: Optional[str] = None
    constraint_message: Optional[str] = None
    calculation: Optional[str] = None
    repeat_count: Optional[str] = None
    read_only: Optional[str] = None
    default: Optional[str] = None
    image: Optional[str] = None
    audio: Optional[str] = None
    media_audio: Optional[str] = None
    media_video: Optional[str] = None
    timestamp_req: Optional[str] = None
    fetch_data_from_riptide: Optional[str] = None
    fetch_data_for_field_name: Optional[str] = None
    riptide_api_prop_name: Optional[str] = None
    fetch_unit_tag_from_field_name: Optional[str] = None
    include_in_building_profiles: Optional[str] = None
    equipment_type: Optional[str] = None
    equipment_code: Optional[str] = None
    constraint_check: Optional[str] = None
    order: Optional[str] = None
    alias: Optional[str] = None

class PaginationParams(BaseModel):
    """Pagination parameters"""
    page: int = Field(1, ge=1, description="Page number (starts from 1)")
    per_page: int = Field(20, ge=1, le=100, description="Items per page")

class SurveyFieldResponse(BaseModel):
    """Response model for paginated survey fields"""
    fields: List[SurveyField]
    total: int
    page: int
    per_page: int
    total_pages: int

class FieldTypeInfo(BaseModel):
    """Information about field types in the survey"""
    type: str
    count: int
    description: Optional[str] = ""

class SurveyStats(BaseModel):
    """Statistics about the survey"""
    total_fields: int
    field_types: List[FieldTypeInfo]
    required_fields_count: int
    has_media_fields: bool

class Choice(BaseModel):
    """Model representing a choice option for select fields"""
    id: Optional[int] = Field(None, description="Auto-generated ID")
    label: str = Field(..., description="Display text for the choice")
    name: str = Field(..., description="Internal value for the choice")
    list_name: Optional[str] = Field("", description="Name of the choice list this belongs to")
    order: Optional[int] = Field(None, description="Display order")

class ChoiceCreate(BaseModel):
    """Model for creating a new choice"""
    label: str = Field(..., min_length=1, description="Display text")
    name: str = Field(..., min_length=1, description="Internal value")
    list_name: str = Field(..., min_length=1, description="Choice list name")
    order: Optional[int] = None

class ChoiceUpdate(BaseModel):
    """Model for updating an existing choice"""
    label: Optional[str] = None
    name: Optional[str] = None
    list_name: Optional[str] = None
    order: Optional[int] = None

class ChoiceList(BaseModel):
    """Model representing a complete choice list"""
    list_name: str
    choice_type: str  # 'select_one' or 'select_multiple'
    choices: List[Choice]
    total_choices: int

class FormSettings(BaseModel):
    """Model representing form-level settings"""
    form_title: Optional[str] = Field("", description="Title of the form")
    form_id: Optional[str] = Field("", description="Unique form identifier")
    style: Optional[str] = Field("", description="Form styling theme")
    version: Optional[int] = Field(None, description="Form version number")
    run_diagnostic: Optional[bool] = Field(False, description="Enable diagnostics")
    send_reports: Optional[bool] = Field(False, description="Enable report sending")
    integration: Optional[str] = Field("", description="Integration platform")

class FormSettingsUpdate(BaseModel):
    """Model for updating form settings"""
    form_title: Optional[str] = None
    form_id: Optional[str] = None
    style: Optional[str] = None
    version: Optional[int] = None
    run_diagnostic: Optional[bool] = None
    send_reports: Optional[bool] = None
    integration: Optional[str] = None

class XLSFormData(BaseModel):
    """Complete XLSForm data structure"""
    survey_fields: List[SurveyField]
    select_one_choices: List[Choice]
    select_multiple_choices: List[Choice]
    settings: FormSettings
    
class XLSFormStats(BaseModel):
    """Comprehensive statistics about the XLSForm"""
    total_fields: int
    total_select_one_choices: int
    total_select_multiple_choices: int
    unique_choice_lists: int
    field_types: List[FieldTypeInfo]
    form_info: FormSettings
