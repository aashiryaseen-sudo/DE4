import os
import tempfile
from typing import Any, List
import xml.etree.ElementTree as ET

from database.models import FormChoice, FormField, FormVersion


class FormExporter:
    """
    Builds a valid XLSForm XML file from a FormVersion database object.
    """

    def __init__(self, version_obj: FormVersion):
        self.version_obj = version_obj
        self.form_obj = version_obj.form

        # Register the XML namespaces
        self.namespaces = {
            "ss": "urn:schemas-microsoft-com:office:spreadsheet",
            "o": "urn:schemas-microsoft-com:office:office",
            "x": "urn:schemas-microsoft-com:office:excel",
            "html": "http://www.w3.org/TR/REC-html40",
        }
        for prefix, uri in self.namespaces.items():
            ET.register_namespace(prefix, uri)

        # Create the XML root elements
        self.root = ET.Element("Workbook", xmlns=self.namespaces["ss"])
        self.root.set("xmlns:o", self.namespaces["o"])
        self.root.set("xmlns:x", self.namespaces["x"])
        self.root.set("xmlns:html", self.namespaces["html"])

    def _create_worksheet(self, name: str) -> ET.Element:
        """Helper to create a worksheet element."""
        ws = ET.SubElement(self.root, "Worksheet")
        ws.set(f"{{{self.namespaces['ss']}}}Name", name)
        table = ET.SubElement(ws, "Table")
        return table

    def _create_cell(self, row_elem: ET.Element, data: Any, ss_type: str = "String"):
        """Helper to create a cell with data."""
        if data is None:
            data = ""  # Ensure we have a string, not None

        cell = ET.SubElement(row_elem, "Cell")
        data_elem = ET.SubElement(cell, "Data")
        data_elem.set(f"{{{self.namespaces['ss']}}}Type", ss_type)
        data_elem.text = str(data)
        return cell

    def _create_row_from_list(self, table_elem: ET.Element, data_list: List[str]):
        """Helper to create a full row from a list of strings."""
        row = ET.SubElement(table_elem, "Row")
        for item in data_list:
            self._create_cell(row, item)
        return row

    def _populate_survey_sheet(self):
        """Builds the 'survey' worksheet from the form_fields table."""
        ws_table = self._create_worksheet("survey")

        # Get all column names from the FormField model and spec
        # This MUST match the full spec.
        headers = [
            "name",
            "type",
            "label",
            "appearance",
            "required",
            "relevant",
            "hint",
            "constraint_formula",
            "constraint_message",
            "calculation",
            "repeat_count",
            "read_only",
            "default_value",
            "image",
            "audio",
            "media::audio",
            "media::video",
            "timestamp_req",
            "fetch_data_from_riptide",
            "fetch_data_for_field_name",
            "riptide_api_prop_name",
            "fetch_unit_tag_from_field_name",
            "include_in_building_profiles",
            "equipment_type",
            "equipment_code",
            "fetch_heat_type_from_field_name",
            "fetch_priority_array_from_riptide",
            "riptide_timed_override",
            "fetch_override_temp_from_field_name",
            "cancel_riptide_timed_override",
            "constraint_check",
            "field_order",
            "alias",
        ]

        self._create_row_from_list(ws_table, headers)

        # Loop through all sorted fields and build the rows
        sorted_fields = sorted(self.version_obj.fields, key=lambda f: f.field_order or 999)
        for field in sorted_fields:
            row = ET.SubElement(ws_table, "Row")
            # Iterate headers to ensure correct column order, mapping DB names to XML headers
            for header in headers:
                data = None
                if header == "constraint":
                    data = getattr(field, "constraint_formula", "")
                elif header == "default":
                    data = getattr(field, "default_value", "")
                elif header == "order":
                    data = getattr(field, "field_order", "")
                elif header == "media::audio":
                    data = getattr(field, "media_audio", "")
                elif header == "media::video":
                    data = getattr(field, "media_video", "")
                else:
                    data = getattr(field, header, "")  # Get attribute, default to empty string

                # Convert booleans to uppercase 'TRUE'/'FALSE' for XLSForm spec
                if isinstance(data, bool):
                    data = "TRUE" if data else "FALSE"

                self._create_cell(row, data)

    def _populate_choice_sheets(self):
        """Builds both select_one and select_multiple sheets."""
        choice_headers = ["list_name", "name", "label"]

        # Create both sheets
        ws_one_table = self._create_worksheet("select_one")
        ws_multi_table = self._create_worksheet("select_multiple")

        # Add headers to both
        self._create_row_from_list(ws_one_table, choice_headers)
        self._create_row_from_list(ws_multi_table, choice_headers)

        # Write all choices from the DB to BOTH sheets
        # This matches the (inefficient but safe) original XML structure
        if self.version_obj.choices:
            for choice in self.version_obj.choices:
                choice_data = [choice.list_name, choice.name, choice.label]
                self._create_row_from_list(ws_one_table, choice_data)
                self._create_row_from_list(ws_multi_table, choice_data)

    def _populate_settings_sheet(self):
        """Builds the 'settings' worksheet."""
        ws_table = self._create_worksheet("settings")

        # Settings headers and data row
        setting_headers = ["form_title", "form_id", "version", "style"]  # Add more as needed
        self._create_row_from_list(ws_table, setting_headers)

        setting_data = [
            self.form_obj.title,
            self.form_obj.form_id_string,
            self.version_obj.version_string,
            "theme-grid",  # Example default style
        ]
        self._create_row_from_list(ws_table, setting_data)

    def build_xml(self) -> str:
        """
        Builds all worksheets, saves to a temp file, and returns the path.
        """
        # Build all components of the workbook
        self._populate_settings_sheet()
        self._populate_survey_sheet()
        self._populate_choice_sheets()

        # Create a secure temporary file
        # suffix='.xml' ensures the correct file extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml", mode="wb") as temp_f:
            tree = ET.ElementTree(self.root)
            tree.write(temp_f, encoding="utf-8", xml_declaration=True)
            return temp_f.name  # Return the path to the temp file
