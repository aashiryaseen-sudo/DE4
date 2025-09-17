"""
Production XML Editor for XLSForm modifications
Applies real changes to XML structure based on AI operations
"""

import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional


class XLSFormXMLEditor:
    """
    Production-ready XML editor that applies actual changes to XLSForm XML files
    """

    def __init__(self, xml_file_path: str):
        self.original_xml_path = xml_file_path
        self.tree = ET.parse(xml_file_path)
        self.root = self.tree.getroot()
        self.namespaces = {
            "ss": "urn:schemas-microsoft-com:office:spreadsheet",
            "o": "urn:schemas-microsoft-com:office:office",
            "x": "urn:schemas-microsoft-com:office:excel",
            "html": "http://www.w3.org/TR/REC-html40",
        }
        self.edit_history = []
        self.modified = False

    def get_tree(self):
        """Get the XML tree for external access"""
        return self.tree

    def find_worksheet(self, worksheet_name: str) -> Optional[ET.Element]:
        """Find a worksheet by name"""
        for worksheet in self.root.findall(".//ss:Worksheet", self.namespaces):
            name_attr = worksheet.get("{urn:schemas-microsoft-com:office:spreadsheet}Name")
            if name_attr == worksheet_name:
                return worksheet
        return None

    def find_table_in_worksheet(self, worksheet: ET.Element) -> Optional[ET.Element]:
        """Find the table element in a worksheet"""
        return worksheet.find(".//ss:Table", self.namespaces)

    def get_headers(self, table: ET.Element) -> List[str]:
        """Get headers from the first row of a table"""
        rows = table.findall(".//ss:Row", self.namespaces)
        if not rows:
            return []

        header_row = rows[0]
        headers = []
        cells = header_row.findall(".//ss:Cell", self.namespaces)

        for cell in cells:
            data_elem = cell.find(".//ss:Data", self.namespaces)
            header_text = data_elem.text if data_elem is not None and data_elem.text else ""
            headers.append(header_text)

        return headers

    def _iter_worksheets(self) -> List[ET.Element]:
        """Return all worksheet elements."""
        return self.root.findall(".//ss:Worksheet", self.namespaces)

    def detect_choice_worksheets(self) -> List[str]:
        """Detect worksheets that look like choice lists by header patterns.

        Heuristics:
        - Must have a table with headers containing at least 'label' and 'name' (any case)
        - Optionally contains 'list name' or 'list_name' or similar
        Returns worksheet names ordered by strength of match (strongest first).
        """
        candidates: List[tuple[int, str]] = []
        for ws in self._iter_worksheets():
            ws_name = ws.get("{urn:schemas-microsoft-com:office:spreadsheet}Name") or ""
            table = self.find_table_in_worksheet(ws)
            if table is None:
                continue
            headers = [h.lower().strip() for h in self.get_headers(table)]
            if not headers:
                continue
            has_label = any("label" == h or h.startswith("label") for h in headers)
            has_name = any(h == "name" or h.endswith(":name") or "name" == h for h in headers)
            has_list = any(h.replace(" ", "_") in ("list_name", "listname") or h == "list name" for h in headers)
            score = (2 if has_label else 0) + (2 if has_name else 0) + (1 if has_list else 0)
            if score >= 3:  # needs at least label+name
                candidates.append((score, ws_name))
        # sort by score desc
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [name for _, name in candidates]

    def find_rows_by_pattern(self, worksheet_name: str, column_index: int, pattern: str) -> List[ET.Element]:
        """Find rows where a specific column matches a pattern"""
        worksheet = self.find_worksheet(worksheet_name)
        if not worksheet:
            return []

        table = self.find_table_in_worksheet(worksheet)
        if not table:
            return []

        matching_rows = []
        rows = table.findall(".//ss:Row", self.namespaces)

        # Skip header row (index 0)
        for row in rows[1:]:
            cells = row.findall(".//ss:Cell", self.namespaces)
            if column_index < len(cells):
                cell = cells[column_index]
                data_elem = cell.find(".//ss:Data", self.namespaces)
                if data_elem is not None and data_elem.text:
                    if re.search(pattern, data_elem.text, re.IGNORECASE):
                        matching_rows.append(row)

        return matching_rows

    def remove_row(self, worksheet_name: str, row_element: ET.Element) -> bool:
        """Remove a specific row from a worksheet"""
        try:
            worksheet = self.find_worksheet(worksheet_name)
            if not worksheet:
                return False

            table = self.find_table_in_worksheet(worksheet)
            if not table:
                return False

            # Remove the row
            table.remove(row_element)

            # Update row count
            current_count = int(table.get("{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount", "0"))
            if current_count > 0:
                table.set("{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount", str(current_count - 1))

            self.modified = True
            return True

        except Exception as e:
            print(f"Error removing row: {str(e)}")
            return False

    def add_row(self, worksheet_name: str, row_data: List[str], insert_position: str = "end") -> bool:
        """Add a new row to a worksheet"""
        try:
            worksheet = self.find_worksheet(worksheet_name)
            if not worksheet:
                return False

            table = self.find_table_in_worksheet(worksheet)
            if not table:
                return False

            # Create new row element
            new_row = ET.Element("{urn:schemas-microsoft-com:office:spreadsheet}Row")

            # Add cells to the row
            for i, cell_data in enumerate(row_data):
                cell = ET.SubElement(new_row, "{urn:schemas-microsoft-com:office:spreadsheet}Cell")
                data = ET.SubElement(cell, "{urn:schemas-microsoft-com:office:spreadsheet}Data")
                data.set("{urn:schemas-microsoft-com:office:spreadsheet}Type", "String")
                data.text = str(cell_data)

            # Insert the row
            if insert_position == "end":
                table.append(new_row)
            else:
                # Insert at beginning (after header)
                rows = table.findall(".//ss:Row", self.namespaces)
                if len(rows) > 0:
                    # Insert after header row
                    table.insert(1, new_row)
                else:
                    table.append(new_row)

            # Update row count
            current_count = int(table.get("{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount", "0"))
            table.set("{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount", str(current_count + 1))

            self.modified = True
            return True

        except Exception as e:
            print(f"Error adding row: {str(e)}")
            return False

    def add_row_generic(self, worksheet_name: str, row_values: List[str]) -> bool:
        """Add a row using provided values, aligned to the worksheet headers length.
        Extra values are truncated; missing values are padded with empty strings.
        """
        worksheet = self.find_worksheet(worksheet_name)
        if not worksheet:
            return False
        table = self.find_table_in_worksheet(worksheet)
        if not table:
            return False
        headers = self.get_headers(table)
        num_cols = len(headers) if headers else len(row_values)
        normalized = (row_values + [""] * num_cols)[:num_cols]
        return self.add_row(worksheet_name, normalized)

    def add_row_to_best_match(self, row_values: List[str], sheet_hint: Optional[str] = None) -> Dict[str, Any]:
        """Add a row to the best matching worksheet based on header count/keywords.

        - If sheet_hint matches an existing worksheet, prefer it.
        - Else choose worksheet with header count closest to len(row_values) and with highest overlap
          with simple keywords like label/name/list name for choice-like tables or known settings keys.
        """
        target_ws = None
        target_score = -1
        target_headers: List[str] = []
        desired_len = len(row_values)

        # First pass: exact name hint
        if sheet_hint:
            ws = self.find_worksheet(sheet_hint)
            if ws is not None:
                table = self.find_table_in_worksheet(ws)
                if table is not None:
                    headers = [h.lower().strip() for h in self.get_headers(table)]
                    if headers:
                        target_ws = sheet_hint
                        target_headers = headers
                        target_score = 100  # strong preference

        # Second pass: heuristic scoring across all worksheets
        for ws in self._iter_worksheets():
            ws_name = ws.get("{urn:schemas-microsoft-com:office:spreadsheet}Name") or ""
            table = self.find_table_in_worksheet(ws)
            if table is None:
                continue
            headers = [h.lower().strip() for h in self.get_headers(table)]
            if not headers:
                continue
            hdr_len = len(headers)
            # score by closeness of length and keyword overlap
            len_score = max(0, 10 - abs(hdr_len - desired_len))
            keywords = {
                "form_title",
                "form_id",
                "style",
                "version",
                "run_diagnostic",
                "send_reports",
                "integration",
                "label",
                "name",
                "list name",
                "list_name",
            }
            overlap = sum(1 for h in headers if h in keywords)
            score = len_score + overlap
            if score > target_score:
                target_score = score
                target_ws = ws_name
                target_headers = headers

        if not target_ws:
            return {"success": False, "message": "No compatible worksheet found"}

        ok = self.add_row_generic(target_ws, row_values)
        return {"success": ok, "worksheet": target_ws, "headers": target_headers}

    def add_choice_option(self, list_name: str, label: str, name: str, worksheet_name: str = None) -> bool:
        """Add a new choice option to select_one or select_multiple lists"""
        try:
            # Determine which worksheet(s) to use
            if worksheet_name is None:
                worksheets_to_try = self.detect_choice_worksheets()
            else:
                worksheets_to_try = [worksheet_name]

            for ws_name in worksheets_to_try:
                worksheet = self.find_worksheet(ws_name)
                if not worksheet:
                    continue

                table = self.find_table_in_worksheet(worksheet)
                if not table:
                    continue

                # Get headers to understand the structure
                headers = self.get_headers(table)
                if len(headers) < 3:  # Need at least list_name, name, label columns
                    continue

                print(f"🔍 Headers in {ws_name}: {headers}")

                # Create new choice row based on actual header structure
                # Common XLSForm structures:
                # ['label', 'name', 'list name', 'order'] - most common
                # ['list_name', 'name', 'label'] - alternative

                if len(headers) >= 4 and "list name" in [h.lower() for h in headers]:
                    # Standard XLSForm structure: [label, name, list_name, order]
                    choice_row_data = [label, name, list_name, ""]  # Empty order
                    print(f"Using standard XLSForm structure: {choice_row_data}")
                elif len(headers) >= 3:
                    # Fallback structure: [list_name, name, label]
                    choice_row_data = [list_name, name, label]
                    print(f"Using fallback structure: {choice_row_data}")
                else:
                    print(f"❌ Insufficient headers in {ws_name}: {headers}")
                    continue

                # Add the new choice option
                if self.add_row(ws_name, choice_row_data):
                    print(f"Added choice option '{label}' to list '{list_name}' in worksheet '{ws_name}'")
                    return True

            return False

        except Exception as e:
            print(f"Error adding choice option: {str(e)}")
            return False

    def add_choice_options_batch(
        self, list_name: str, items: List[Dict[str, str]], worksheet_name: str = None
    ) -> Dict[str, Any]:
        """Batch add multiple choice options in one pass; saves once at caller.

        items: list of dicts with keys: label, name (name optional; generated from label if missing)
        """
        added = 0
        failures: List[Dict[str, str]] = []
        # choose worksheet once using detection for consistency
        target_ws = None
        if worksheet_name is None:
            candidates = self.detect_choice_worksheets()
            if candidates:
                target_ws = candidates[0]
        else:
            target_ws = worksheet_name

        for item in items:
            lab = str(item.get("label", "")).strip()
            nm = str(item.get("name", "")).strip() or re.sub(r"[^A-Za-z0-9_]+", "_", lab).strip("_")
            if not lab:
                failures.append({"label": lab, "name": nm, "reason": "missing label"})
                continue
            ok = self.add_choice_option(list_name=list_name, label=lab, name=nm, worksheet_name=target_ws)
            if ok:
                added += 1
            else:
                failures.append({"label": lab, "name": nm, "reason": "insert failed"})
        return {"added": added, "failed": failures, "modified": self.modified}

    def modify_choice_property(self, list_name: str, choice_name: str, property_name: str, new_value: str) -> bool:
        """
        Modify a property (commonly 'label' or 'name') of a choice row where list_name == list_name and name == choice_name.

        - Searches worksheets detected by detect_choice_worksheets()
        - Supports common header variants: ['label','name','list name','order'] or ['list_name','name','label']
        - Returns True if at least one matching row is updated
        """
        try:
            updated = 0

            # Gather candidate worksheets that look like choices
            candidates = self.detect_choice_worksheets()
            for ws_name in candidates:
                worksheet = self.find_worksheet(ws_name)
                if worksheet is None:
                    continue
                table = self.find_table_in_worksheet(worksheet)
                if table is None:
                    continue

                headers = [h.lower().strip() for h in self.get_headers(table)]
                if not headers:
                    continue

                # Helper to map header aliases
                def idx_of(*aliases: str) -> int:
                    for a in aliases:
                        if a in headers:
                            return headers.index(a)
                    return -1

                list_idx = idx_of("list name", "list_name")
                name_idx = idx_of("name")
                label_idx = idx_of("label")
                order_idx = idx_of("order")

                if list_idx == -1 or name_idx == -1:
                    continue

                rows = table.findall(".//ss:Row", self.namespaces)
                for row in rows[1:]:  # skip header row
                    cells = row.findall(".//ss:Cell", self.namespaces)
                    # Build sparse mapping index->text honoring ss:Index
                    expanded: Dict[int, str] = {}
                    current_idx = 0
                    for cell in cells:
                        index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                        if index_attr:
                            current_idx = int(index_attr) - 1
                        data_elem = cell.find(".//ss:Data", self.namespaces)
                        expanded[current_idx] = data_elem.text if data_elem is not None else ""
                        current_idx += 1

                    row_list = (expanded.get(list_idx, "") or "").strip()
                    row_name = (expanded.get(name_idx, "") or "").strip()
                    if row_list == str(list_name).strip() and row_name == str(choice_name).strip():
                        # Determine target column
                        target_col = None
                        prop = property_name.lower().strip()
                        if prop == "label" and label_idx != -1:
                            target_col = label_idx
                        elif prop == "name":
                            target_col = name_idx
                        elif prop == "order" and order_idx != -1:
                            target_col = order_idx
                        else:
                            # Unsupported property for this row structure
                            continue

                        # Locate or create the target cell honoring ss:Index
                        target_cell = None
                        current_idx = 0
                        for cell in cells:
                            index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                            if index_attr:
                                current_idx = int(index_attr) - 1
                            if current_idx == target_col:
                                target_cell = cell
                                break
                            if current_idx > target_col:
                                break
                            current_idx += 1

                        if target_cell is None:
                            # Insert a new cell with ss:Index at the correct position
                            target_cell = ET.Element(f"{{{self.namespaces['ss']}}}Cell")
                            target_cell.set(f"{{{self.namespaces['ss']}}}Index", str(target_col + 1))

                            # Insert preserving order
                            inserted = False
                            for idx, cell in enumerate(cells):
                                idx_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                                if idx_attr and int(idx_attr) - 1 > target_col:
                                    row.insert(idx, target_cell)
                                    inserted = True
                                    break
                            if not inserted:
                                row.append(target_cell)

                        data_elem = target_cell.find(f".//ss:Data", self.namespaces)
                        if data_elem is None:
                            data_elem = ET.SubElement(target_cell, f"{{{self.namespaces['ss']}}}Data")
                            data_elem.set(f"{{{self.namespaces['ss']}}}Type", "String")
                        data_elem.text = str(new_value)
                        updated += 1

            if updated > 0:
                self.modified = True
                print(f" Updated {updated} choice row(s) for list '{list_name}', choice '{choice_name}' – set {property_name} -> {new_value}.")
                return True
            else:
                print(f" WARN: No matching choice found for list '{list_name}', choice '{choice_name}'.")
                return False
        except Exception as e:
            print(f" ERROR in modify_choice_property: {str(e)}")
            return False

    def modify_cell(self, worksheet_name: str, row_index: int, column_index: int, new_value: str) -> bool:
        """Modify a specific cell value"""
        try:
            worksheet = self.find_worksheet(worksheet_name)
            if not worksheet:
                return False

            table = self.find_table_in_worksheet(worksheet)
            if not table:
                return False

            rows = table.findall(".//ss:Row", self.namespaces)
            if row_index >= len(rows):
                return False

            row = rows[row_index]
            cells = row.findall(".//ss:Cell", self.namespaces)

            if column_index >= len(cells):
                # Need to add new cells
                for i in range(len(cells), column_index + 1):
                    new_cell = ET.SubElement(row, "{urn:schemas-microsoft-com:office:spreadsheet}Cell")
                    new_data = ET.SubElement(new_cell, "{urn:schemas-microsoft-com:office:spreadsheet}Data")
                    new_data.set("{urn:schemas-microsoft-com:office:spreadsheet}Type", "String")
                    new_data.text = ""

                cells = row.findall(".//ss:Cell", self.namespaces)

            # Modify the cell
            cell = cells[column_index]
            data_elem = cell.find(".//ss:Data", self.namespaces)
            if data_elem is not None:
                data_elem.text = str(new_value)
            else:
                # Create new data element
                data_elem = ET.SubElement(cell, "{urn:schemas-microsoft-com:office:spreadsheet}Data")
                data_elem.set("{urn:schemas-microsoft-com:office:spreadsheet}Type", "String")
                data_elem.text = str(new_value)

            self.modified = True
            return True

        except Exception as e:
            print(f"Error modifying cell: {str(e)}")
            return False

    def _remove_choices_by_list_name(self, list_name: str) -> int:
        """
        Removes all choice options associated with a given list_name from both
        select_one and select_multiple worksheets.

        """
        deleted_count = 0
        worksheets_to_check = ["select_one", "select_multiple"]

        for sheet_name in worksheets_to_check:
            worksheet = self.find_worksheet(sheet_name)
            if worksheet is None:
                continue

            table = self.find_table_in_worksheet(worksheet)
            if table is None:
                continue

            try:
                headers = self.get_headers(table)
                list_name_col_index = headers.index("list_name")
            except (ValueError, IndexError):
                continue

            rows_to_delete = []
            all_rows = table.findall(".//ss:Row", self.namespaces)

            for row in all_rows[1:]:  # Skip header
                cells = row.findall(".//ss:Cell", self.namespaces)
                if len(cells) > list_name_col_index:
                    cell = cells[list_name_col_index]
                    data_elem = cell.find(".//ss:Data", self.namespaces)
                    if data_elem is not None and data_elem.text == list_name:
                        rows_to_delete.append(row)

            if rows_to_delete:
                for row in rows_to_delete:
                    table.remove(row)

                deleted_count += len(rows_to_delete)

                # Update table row count
                current_count = int(table.get("{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount", "0"))
                table.set(
                    "{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount",
                    str(max(0, current_count - len(rows_to_delete))),
                )
                self.modified = True

        if deleted_count > 0:
            print(f" cascade deleted {deleted_count} choices for list '{list_name}'.")
        return deleted_count

    def remove_field_by_name(self, field_name: str) -> bool:
        """
        Finds and removes a field (row) from the 'survey' worksheet by its unique name.
        """
        try:
            worksheet = self.find_worksheet("survey")
            if worksheet is None:
                print("ERROR: 'survey' worksheet not found.")
                return False

            table = self.find_table_in_worksheet(worksheet)
            if table is None:
                print("ERROR: Table not found in 'survey' worksheet.")
                return False

            headers = self.get_headers(table)
            try:
                name_column_index = headers.index("name")
                type_column_index = headers.index("type")
            except ValueError:
                print("ERROR: 'name' or 'type' column not found in survey headers.")
                return False

            row_to_delete = None
            all_rows = table.findall(".//ss:Row", self.namespaces)
            data_rows = all_rows[1:]
            for row in data_rows:
                cells = row.findall(".//ss:Cell", self.namespaces)
                if len(cells) > name_column_index:
                    cell = cells[name_column_index]
                    data_elem = cell.find(".//ss:Data", self.namespaces)
                    if data_elem is not None and data_elem.text == field_name:
                        row_to_delete = row
                        break

            if row_to_delete is not None:
                print(f"Scanning all cells for dependencies of field '{field_name}'...")
                dependency_pattern = f"${{{field_name}}}"
                cleared_count = 0
                for other_row in data_rows:
                    if other_row == row_to_delete:
                        continue
                    for cell_to_check in other_row.findall(".//ss:Cell", self.namespaces):
                        data_elem = cell_to_check.find(".//ss:Data", self.namespaces)
                        if data_elem is not None and data_elem.text and dependency_pattern in data_elem.text:
                            data_elem.text = ""
                            self.modified = True
                            cleared_count += 1

                cells = row_to_delete.findall(".//ss:Cell", self.namespaces)
                if len(cells) > type_column_index:
                    type_cell = cells[type_column_index]
                    type_data_elem = type_cell.find(".//ss:Data", self.namespaces)
                    if type_data_elem is not None and type_data_elem.text:
                        type_string = type_data_elem.text
                        # Use regex to find and extract the list_name
                        match = re.match(r"^(select_one|select_multiple)\s+(\S+)", type_string)
                        if match:
                            list_name_to_delete = match.group(2)
                            print(
                                f"ℹ Field '{field_name}' is a select type. Looking for choices from list '{list_name_to_delete}' to delete."
                            )
                            self._remove_choices_by_list_name(list_name_to_delete)

                table.remove(row_to_delete)

                current_count = int(table.get("{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount", "0"))
                if current_count > 0:
                    table.set("{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount", str(current_count - 1))

                self.modified = True
                print(f"Successfully found and removed field: {field_name}")
                return True
            else:
                print(f"WARN: Field '{field_name}' not found in survey.")
                return False

        except Exception as e:
            print(f"ERROR in remove_field_by_name: {str(e)}")
            return False

    def modify_field_property(self, field_name: str, property_name: str, new_value: str) -> bool:
        """
        Finds a field in the survey sheet by its name and modifies one of its properties.
        """
        try:
            worksheet = self.find_worksheet("survey")
            if worksheet is None:
                print("ERROR: 'survey' worksheet not found.")
                return False

            table = self.find_table_in_worksheet(worksheet)
            if table is None:
                print("ERROR: Table not found in 'survey' worksheet.")
                return False

            headers = self.get_headers(table)
            try:
                name_col_index = headers.index("name")
                prop_col_index = headers.index(property_name)
            except ValueError:
                print(f"ERROR: Column 'name' or '{property_name}' not found in survey headers.")
                return False

            target_row = None
            rows = table.findall(".//ss:Row", self.namespaces)

            # Find the target row based on field_name
            for row in rows[1:]:
                cells = row.findall(".//ss:Cell", self.namespaces)
                if len(cells) > name_col_index:
                    cell = cells[name_col_index]
                    data_elem = cell.find(".//ss:Data", self.namespaces)
                    if data_elem is not None and data_elem.text == field_name:
                        target_row = row
                        break

            if target_row is None:
                print(f" WARN: Field '{field_name}' not found in survey.")
                return False

            # Find and update the specific cell for the property
            # This logic handles sparse XML where cells might not exist in order
            target_cell = None
            current_idx = 0
            cells_in_row = target_row.findall(".//ss:Cell", self.namespaces)

            for i, cell in enumerate(cells_in_row):
                index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                if index_attr:
                    current_idx = int(index_attr) - 1

                if current_idx == prop_col_index:
                    target_cell = cell
                    break

                # If we've passed the target index, the cell doesn't exist yet
                if current_idx > prop_col_index:
                    # Create and insert the cell at the correct position
                    target_cell = ET.Element(f"{{{self.namespaces['ss']}}}Cell")
                    target_cell.set(f"{{{self.namespaces['ss']}}}Index", str(prop_col_index + 1))
                    target_row.insert(i, target_cell)
                    break

                current_idx += 1

            if target_cell is None:
                target_cell = ET.SubElement(target_row, f"{{{self.namespaces['ss']}}}Cell")

            data_elem = target_cell.find(f".//ss:Data", self.namespaces)
            if data_elem is None:
                data_elem = ET.SubElement(target_cell, f"{{{self.namespaces['ss']}}}Data")
                data_elem.set(f"{{{self.namespaces['ss']}}}Type", "String")

            data_elem.text = str(new_value)

            self.modified = True
            print(f" Successfully modified property '{property_name}' for field '{field_name}'.")
            return True

        except Exception as e:
            print(f" ERROR in modify_field_property: {str(e)}")
            return False

    def execute_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single edit operation"""
        operation_type = operation.get("operation_type")
        target_sheet = operation.get("target_sheet")
        target_field = operation.get("target_field")

        result = {"operation": operation, "success": False, "message": "", "timestamp": datetime.now().isoformat()}

        try:
            if operation_type == "remove":
                # Remove fields matching the target field pattern
                if target_sheet and target_field:
                    # Find rows in the first column (field names) that match the pattern
                    matching_rows = self.find_rows_by_pattern(target_sheet, 0, re.escape(target_field))

                    removed_count = 0
                    for row in matching_rows:
                        if self.remove_row(target_sheet, row):
                            removed_count += 1

                    result["success"] = removed_count > 0
                    result["message"] = (
                        f"Removed {removed_count} fields matching '{target_field}' from '{target_sheet}'"
                    )

            elif operation_type == "add":
                # Check if this is adding a choice option or a field
                if "choice_option" in operation:
                    # Adding a choice option to select_one/select_multiple
                    choice_data = operation.get("choice_option", {})
                    list_name = choice_data.get("list_name", target_field)
                    label = choice_data.get("label", target_field)
                    name = choice_data.get("name", target_field)
                    worksheet_name = choice_data.get("worksheet", target_sheet)

                    if self.add_choice_option(list_name, label, name, worksheet_name):
                        result["success"] = True
                        result["message"] = f"Added choice option '{label}' (name: '{name}') to list '{list_name}'"
                    else:
                        result["message"] = f"Failed to add choice option '{label}' to list '{list_name}'"

                else:
                    # Add new field
                    if target_sheet and target_field:
                        new_value = operation.get("new_value")
                        if new_value:
                            try:
                                field_data = json.loads(new_value)
                                row_data = [
                                    field_data.get("name", target_field),
                                    field_data.get("type", "text"),
                                    field_data.get("label", target_field),
                                ]

                                if self.add_row(target_sheet, row_data):
                                    result["success"] = True
                                    result["message"] = f"Added new field '{target_field}' to '{target_sheet}'"
                                else:
                                    result["message"] = f"Failed to add field '{target_field}' to '{target_sheet}'"
                            except json.JSONDecodeError:
                                result["message"] = f"Invalid field data format for '{target_field}'"
                        else:
                            result["message"] = f"No field data provided for '{target_field}'"

            elif operation_type == "modify":
                # Modify existing field
                if target_sheet and target_field:
                    new_value = operation.get("new_value")
                    if new_value:
                        # Find the field and modify it
                        matching_rows = self.find_rows_by_pattern(target_sheet, 0, re.escape(target_field))

                        modified_count = 0
                        for row in matching_rows:
                            # Modify the second column (type) or third column (label) based on operation
                            # This is a simplified implementation
                            cells = row.findall(".//ss:Cell", self.namespaces)
                            if len(cells) > 1:
                                data_elem = cells[1].find(".//ss:Data", self.namespaces)
                                if data_elem is not None:
                                    data_elem.text = str(new_value)
                                    modified_count += 1

                        result["success"] = modified_count > 0
                        result["message"] = (
                            f"Modified {modified_count} instances of '{target_field}' in '{target_sheet}'"
                        )
                    else:
                        result["message"] = f"No new value provided for '{target_field}'"

            else:
                result["message"] = f"Unknown operation type: {operation_type}"

        except Exception as e:
            result["message"] = f"Error executing operation: {str(e)}"

        # Add to edit history
        self.edit_history.append(result)
        return result

    def execute_operations(self, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute multiple edit operations"""
        results = []
        success_count = 0

        for operation in operations:
            result = self.execute_operation(operation)
            results.append(result)
            if result["success"]:
                success_count += 1

        return {
            "total_operations": len(operations),
            "successful_operations": success_count,
            "failed_operations": len(operations) - success_count,
            "results": results,
            "modified": self.modified,
            "edit_history": self.edit_history,
        }

    def save_modified_xml(self, output_path: str = None) -> str:
        """Save the modified XML to a new file with timestamp"""
        try:
            from datetime import datetime

            # Generate timestamped filename in the SAME directory as the original by default
            if output_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                original_name = os.path.basename(self.original_xml_path).replace(".xml", "")
                original_dir = os.path.dirname(os.path.abspath(self.original_xml_path))
                output_path = os.path.join(original_dir, f"modified_{original_name}_{timestamp}.xml")

            # Create backup of original if this is the first save
            backup_path = f"{self.original_xml_path}.backup"
            if not os.path.exists(backup_path):
                shutil.copy2(self.original_xml_path, backup_path)
                print(f"✅ Backup created: {backup_path}")

            # Write the modified XML
            self.tree.write(output_path, encoding="utf-8", xml_declaration=True, method="xml")

            print(f"✅ Modified XML saved to: {os.path.abspath(output_path)}")
            return os.path.abspath(output_path)

        except Exception as e:
            print(f"❌ Error saving XML: {str(e)}")
            return None

    def get_edit_summary(self) -> Dict[str, Any]:
        """Get a summary of all edits made"""
        return {
            "original_file": self.original_xml_path,
            "modified": self.modified,
            "total_edits": len(self.edit_history),
            "successful_edits": len([e for e in self.edit_history if e["success"]]),
            "edit_history": self.edit_history,
            "timestamp": datetime.now().isoformat(),
        }


# Factory function
def create_xml_editor(xml_file_path: str) -> XLSFormXMLEditor:
    """Create an XML editor instance"""
    return XLSFormXMLEditor(xml_file_path)
