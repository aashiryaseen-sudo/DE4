from sqlalchemy.orm import Session

from database.models import Form, FormChoice, FormField, FormVersion, User
from xml_parser import XLSFormParser


class FormIngestor:
    """
    Parses an uploaded XLSForm XML file and ingests it into the
    relational PostgreSQL database.
    """

    def __init__(self, db: Session, xml_file_path: str, user: User):
        self.db = db
        self.xml_path = xml_file_path
        self.user = user
        self.parser = XLSFormParser(self.xml_path)

    def ingest_form(self) -> FormVersion:
        """
        Main orchestration method. Parses all parts of the XML file
        and commits them to the database in a single transaction.
        """
        try:
            settings = self.parser.parse_settings()
            survey_rows = self.parser.parse_survey_fields()
            select_one_rows = self.parser.parse_choices("select_one")
            select_multiple_rows = self.parser.parse_choices("select_multiple")
            all_choice_rows = select_one_rows + select_multiple_rows

            if not survey_rows or not settings:
                raise ValueError("Form is missing 'settings' or 'survey' data.")

            form_id_str = settings.get("form_id")
            form_version_str = settings.get("version", "1.0")
            form_title = settings.get("form_title", form_id_str)

            db_form = self.db.query(Form).filter(Form.form_id_string == form_id_str).first()
            if not db_form:
                print(f"Creating new master form: {form_id_str}")
                db_form = Form(
                    form_id_string=form_id_str,
                    title=form_title,
                    created_by=self.user.id,
                    # TODO Add other metadata from 'forms' table like tags, desc, etc. if available
                )
                self.db.add(db_form)
                self.db.flush()

            new_version = FormVersion(
                form_id=db_form.id,
                version_string=form_version_str,
                created_by=self.user.id,
                notes="Initial form ingest.",
            )

            field_objects = []

            def get_val(data):
                if isinstance(data, tuple) and len(data) > 0:
                    return data[0]
                return data

            for field_order, field_data in enumerate(survey_rows):
                field_name = get_val(field_data.get("name"))
                field_type = get_val(field_data.get("type"))
                if not field_name or not field_type:
                    continue

                field_obj = FormField(
                    # Core Fields
                    name=field_name,
                    type=field_type,
                    label=field_data.get("label"),
                    appearance=field_data.get("appearance"),
                    # Logic & Validation Fields
                    required=True if field_data.get("required", "").lower() == "true" else False,
                    relevant=field_data.get("relevant"),
                    hint=field_data.get("hint"),
                    constraint_formula=field_data.get("constraint"),  # Map 'constraint' in spec to DB column
                    constraint_message=field_data.get("constraint_message"),
                    calculation=field_data.get("calculation"),
                    read_only=True if field_data.get("read_only", "").lower() == "true" else False,
                    default_value=field_data.get("default"),  # Map 'default' in spec to DB column
                    # Grouping
                    repeat_count=field_data.get("repeat_count"),
                    # Deprecated Media Fields (using the Python-valid attribute names)
                    image=field_data.get("image"),
                    audio=field_data.get("audio"),
                    media_audio=field_data.get("media::audio"),
                    media_video=field_data.get("media::video"),
                    # DigiMEP & Asset Management Fields
                    timestamp_req=True if field_data.get("timestamp_req", "").lower() == "true" else False,
                    include_in_building_profiles=True
                    if field_data.get("include_in_building_profiles", "").lower() == "true"
                    else False,
                    equipment_type=field_data.get("equipment_type"),
                    equipment_code=field_data.get("equipment_code"),
                    # Riptide/Brainbox API Fields
                    fetch_data_from_riptide=True
                    if field_data.get("fetch_data_from_riptide", "").lower() == "true"
                    else False,
                    fetch_data_for_field_name=True
                    if field_data.get("fetch_data_for_field_name", "").lower() == "true"
                    else False,
                    riptide_api_prop_name=field_data.get("riptide_api_prop_name"),
                    fetch_unit_tag_from_field_name=field_data.get("fetch_unit_tag_from_field_name"),
                    fetch_heat_type_from_field_name=field_data.get("fetch_heat_type_from_field_name"),
                    fetch_priority_array_from_riptide=True
                    if field_data.get("fetch_priority_array_from_riptide", "").lower() == "true"
                    else False,
                    riptide_timed_override=True
                    if field_data.get("riptide_timed_override", "").lower() == "true"
                    else False,
                    fetch_override_temp_from_field_name=field_data.get("fetch_override_temp_from_field_name"),
                    cancel_riptide_timed_override=True
                    if field_data.get("cancel_riptide_timed_override", "").lower() == "true"
                    else False,
                    # Report & Display Fields
                    # Defaulting to TRUE (prevent upload) if blank, per the spec
                    constraint_check=False if field_data.get("constraint_check", "").lower() == "false" else True,
                    field_order=field_order,  # Set the order based on the file
                    alias=field_data.get("alias"),
                )
                field_objects.append(field_obj)

            choice_objects = []
            seen_choices = set()
            for choice_data in all_choice_rows:
                list_name = choice_data.get("list name")
                name = choice_data.get("name")
                choice_key = (list_name, name)
                if choice_key not in seen_choices:
                    choice_obj = FormChoice(list_name=list_name, name=name, label=choice_data.get("label"))
                    choice_objects.append(choice_obj)
                    seen_choices.add(choice_key)

            new_version.fields.extend(field_objects)
            new_version.choices.extend(choice_objects)

            self.db.add(new_version)
            self.db.flush()

            db_form.current_version_id = new_version.id

            self.db.commit()

            return new_version

        except Exception as e:
            self.db.rollback()
            print(f"❌ ERROR during form ingest: {e}")
            raise
