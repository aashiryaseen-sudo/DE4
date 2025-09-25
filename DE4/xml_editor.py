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

    def __init__(self, xml_file_path: str, base_original_path: str = None):
        self.working_xml_path = xml_file_path
        self.original_xml_path = base_original_path or xml_file_path
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

    def _ensure_highlight_styles(self) -> None:
        """Ensure Styles exist for highlighting added/modified content.

        - AIAdded: light red background for added rows
        - AIModified: light orange background for modified cells
        """
        try:
            ns = self.namespaces["ss"]
            styles_tag = f"{{{ns}}}Styles"
            style_tag = f"{{{ns}}}Style"
            interior_tag = f"{{{ns}}}Interior"
            id_attr = f"{{{ns}}}ID"
            color_attr = f"{{{ns}}}Color"
            pattern_attr = f"{{{ns}}}Pattern"

            styles = self.root.find(f"./ss:Styles", self.namespaces)
            if styles is None:
                styles = ET.Element(styles_tag)
                # Insert Styles near the top (before Worksheets if possible)
                inserted = False
                for idx, child in enumerate(list(self.root)):
                    if child.tag.endswith("Worksheet"):
                        self.root.insert(idx, styles)
                        inserted = True
                        break
                if not inserted:
                    self.root.insert(0, styles)

            def ensure_style(style_id: str, bg_hex: str) -> None:
                existing = None
                for s in styles.findall(f"./ss:Style", self.namespaces):
                    if s.get(id_attr) == style_id:
                        existing = s
                        break
                if existing is None:
                    s = ET.SubElement(styles, style_tag)
                    s.set(id_attr, style_id)
                    inter = ET.SubElement(s, interior_tag)
                    inter.set(color_attr, bg_hex)
                    inter.set(pattern_attr, "Solid")

            # Light red for additions, light orange for edits
            ensure_style("AIAdded", "#FFC7CE")
            ensure_style("AIModified", "#FFD966")
        except Exception:
            # Non-fatal: highlighting is best-effort
            pass

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
            self._ensure_highlight_styles()
            worksheet = self.find_worksheet(worksheet_name)
            if not worksheet:
                return False

            table = self.find_table_in_worksheet(worksheet)
            if not table:
                return False

            # Create new row element
            new_row = ET.Element("{urn:schemas-microsoft-com:office:spreadsheet}Row")
            # Mark row as AI-added (highlight)
            new_row.set("{urn:schemas-microsoft-com:office:spreadsheet}StyleID", "AIAdded")

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

    def remove_fields_by_filter(self, filter_groups: List[List[Dict]]) -> Dict[str, Any]:
        """
        Finds and removes fields (rows) from the 'survey' worksheet based on a structured filter.
        Handles AND/OR logic.
        """
        try:
            worksheet = self.find_worksheet("survey")
            if not worksheet:
                return {"success": False, "message": "'survey' worksheet not found."}

            table = self.find_table_in_worksheet(worksheet)
            if not table:
                return {"success": False, "message": "Table not found in 'survey' worksheet."}

            headers = self.get_headers(table)
            lower_headers = [h.lower().strip() for h in headers]

            # Map property names to their column index
            prop_to_index = {header: i for i, header in enumerate(lower_headers)}

            rows_to_delete = []
            all_rows = table.findall(".//ss:Row", self.namespaces)
            data_rows = all_rows[1:]

            for row in data_rows:
                # Extract all data from the current row into a dictionary
                row_data = {}
                current_idx = 0
                for cell in row.findall(".//ss:Cell", self.namespaces):
                    index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                    if index_attr:
                        current_idx = int(index_attr) - 1

                    if current_idx < len(headers):
                        header_name = lower_headers[current_idx]
                        data_elem = cell.find(".//ss:Data", self.namespaces)
                        row_data[header_name] = data_elem.text if data_elem is not None else ""
                    current_idx += 1

                # Evaluate if the row matches the filter logic
                # Outer list is OR - if any group matches, the row is a match.
                row_is_a_match = False
                for group in filter_groups:
                    # Inner list is AND - all conditions in a group must be true.
                    group_is_a_match = True
                    for condition in group:
                        prop = condition.get("property")
                        op = condition.get("operator")
                        val = condition.get("value")

                        cell_value = row_data.get(prop, "").lower()

                        condition_is_met = False
                        if op == "equals":
                            condition_is_met = cell_value == val.lower()
                        elif op == "contains":
                            condition_is_met = val.lower() in cell_value
                        elif op == "starts_with":
                            condition_is_met = cell_value.startswith(val.lower())
                        elif op == "ends_with":
                            condition_is_met = cell_value.endswith(val.lower())
                        elif op == "like":
                            # SQL-LIKE semantics: % → any sequence, _ → any single char
                            # Convert to regex and search case-insensitively
                            escaped = re.escape(val)
                            regex_pattern = "^" + escaped.replace("%", ".*").replace("_", ".") + "$"
                            condition_is_met = re.search(regex_pattern, row_data.get(prop, ""), re.IGNORECASE) is not None
                        elif op == "glob":
                            # Shell-style wildcards (*, ?, []) using fnmatch
                            import fnmatch as _fnmatch
                            condition_is_met = _fnmatch.fnmatch(row_data.get(prop, ""), val)
                        elif op == "regex":
                            # Treat value as a regular expression
                            try:
                                condition_is_met = re.search(val, row_data.get(prop, ""), re.IGNORECASE) is not None
                            except re.error:
                                condition_is_met = False
                        else:
                            # Backward-compatible smart wildcard detection if user supplied * or % in value
                            if isinstance(val, str) and ("*" in val or "%" in val or "_" in val):
                                escaped = re.escape(val)
                                regex_pattern = "^" + escaped.replace("%", ".*").replace("_", ".").replace("\\*", ".*") + "$"
                                condition_is_met = re.search(regex_pattern, row_data.get(prop, ""), re.IGNORECASE) is not None
                            else:
                                condition_is_met = cell_value == val.lower()

                        if not condition_is_met:
                            group_is_a_match = False
                            break  # This AND group failed, try the next OR group

                    if group_is_a_match:
                        row_is_a_match = True
                        break  # This OR group passed, no need to check others

                if row_is_a_match:
                    rows_to_delete.append((row, row_data.get("name", "")))

            if not rows_to_delete:
                return {
                    "success": True,
                    "message": "No fields found matching the specified criteria.",
                    "deleted_count": 0,
                }

            # Perform the actual deletions
            for row_element, field_name in rows_to_delete:
                table.remove(row_element)
                # Cascade delete choices if the field was a select type
                if field_name:
                    self._remove_choices_by_list_name(field_name)

            # Update table row count
            current_count = int(table.get("{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount", "0"))
            table.set(
                "{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount",
                str(max(0, current_count - len(rows_to_delete))),
            )
            self.modified = True

            return {
                "success": True,
                "message": f"Successfully removed {len(rows_to_delete)} fields.",
                "deleted_count": len(rows_to_delete),
            }

        except Exception as e:
            return {"success": False, "error": f"An error occurred while removing fields by filter: {str(e)}"}

    def add_choice_option(self, list_name: str, label: str, name: str) -> bool:
        """
        Adds a new choice option. By default, it searches ONLY in 'select_one' and 'select_multiple' sheets.
        It will add the choice to any of those sheets where the list_name is found.
        """
        try:
            was_added_somewhere = False

            worksheets_to_try = ["select_one", "select_multiple"]

            for ws_name in worksheets_to_try:
                worksheet = self.find_worksheet(ws_name)
                if not worksheet:
                    continue

                table = self.find_table_in_worksheet(worksheet)
                if not table:
                    continue

                headers = self.get_headers(table)
                lower_headers = [h.lower().strip() for h in headers]

                # FIX 2: Check if the list_name exists in this sheet before adding.
                try:
                    list_name_col_index = lower_headers.index("list name")
                except ValueError:
                    continue

                list_exists_in_sheet = False
                for row in table.findall(".//ss:Row", self.namespaces)[1:]:  # Skip header
                    cells = row.findall(".//ss:Cell", self.namespaces)
                    current_idx = 0
                    for cell in cells:
                        index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                        if index_attr:
                            current_idx = int(index_attr) - 1

                        if current_idx == list_name_col_index:
                            data_elem = cell.find(".//ss:Data", self.namespaces)
                            if data_elem is not None and data_elem.text == list_name:
                                list_exists_in_sheet = True
                                break
                        current_idx += 1
                    if list_exists_in_sheet:
                        break

                if not list_exists_in_sheet:
                    continue

                # This logic correctly builds the row data based on the sheet's headers
                choice_row_data = []
                if "label" in lower_headers and "name" in lower_headers and "list name" in lower_headers:
                    row_map = {header: "" for header in lower_headers}
                    row_map["label"] = label
                    row_map["name"] = name
                    row_map["list name"] = list_name
                    choice_row_data = [row_map[h.lower().strip()] for h in headers]
                else:
                    continue

                # FIX 3: Do not 'return True' here. Continue checking other sheets.
                if self.add_row(ws_name, choice_row_data):
                    print(f"✅ Added choice option '{label}' to list '{list_name}' in worksheet '{ws_name}'")
                    was_added_somewhere = True

            return was_added_somewhere

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
            ok = self.add_choice_option(
                list_name=list_name,
                label=lab,
                name=nm,
            )
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
            self._ensure_highlight_styles()
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
                        # Highlight modified cell
                        target_cell.set(f"{{{self.namespaces['ss']}}}StyleID", "AIModified")
                        updated += 1

            if updated > 0:
                self.modified = True
                print(
                    f" Updated {updated} choice row(s) for list '{list_name}', choice '{choice_name}' – set {property_name} -> {new_value}."
                )
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
            self._ensure_highlight_styles()
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
            # Highlight modified cell
            cell.set("{urn:schemas-microsoft-com:office:spreadsheet}StyleID", "AIModified")

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
            self._ensure_highlight_styles()
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
                label_column_index = 2
            except ValueError:
                print("ERROR: 'name' or 'type' column not found in survey headers.")
                return False

            row_to_delete = None
            search_mode = "name"
            all_rows = table.findall(".//ss:Row", self.namespaces)
            data_rows = all_rows[1:]
            for row in data_rows:
                cells = row.findall(".//ss:Cell", self.namespaces)
                current_idx = 0
                found_cell = False
                for cell in cells:
                    index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                    if index_attr:
                        current_idx = int(index_attr) - 1
                    if current_idx == name_column_index:
                        data_elem = cell.find(".//ss:Data", self.namespaces)
                        if data_elem is not None and data_elem.text == field_name:
                            row_to_delete = row
                            found_cell = True
                        break
                    current_idx += 1
                if found_cell:
                    break

            if row_to_delete is None:
                search_mode = "label (index 2)"
                print(f"WARN: Field name '{field_name}' not found. Falling back to search by label at index 2.")
                for row in data_rows:
                    cells = row.findall(".//ss:Cell", self.namespaces)
                    current_idx = 0
                    found_cell = False
                    for cell in cells:
                        index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                        if index_attr:
                            current_idx = int(index_attr) - 1

                        if current_idx == label_column_index:  # This will now use index 2
                            data_elem = cell.find(".//ss:Data", self.namespaces)
                            # Match if the search term is *in* the label
                            if data_elem is not None and data_elem.text and field_name in data_elem.text:
                                row_to_delete = row
                                found_cell = True
                                break
                        current_idx += 1
                    if found_cell:
                        break

            if row_to_delete is not None:
                print(f"Found row to delete by {search_mode}.")
                actual_field_name = ""
                actual_field_type_string = ""
                cells = row_to_delete.findall(".//ss:Cell", self.namespaces)
                current_idx = 0
                for cell in cells:
                    index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                    if index_attr:
                        current_idx = int(index_attr) - 1

                    if current_idx == name_column_index:
                        data_elem = cell.find(".//ss:Data", self.namespaces)
                        if data_elem is not None:
                            actual_field_name = data_elem.text
                    elif current_idx == type_column_index:
                        data_elem = cell.find(".//ss:Data", self.namespaces)
                        if data_elem is not None:
                            actual_field_type_string = data_elem.text

                    current_idx += 1

                if not actual_field_name:
                    actual_field_name = field_name
                    print(
                        f"WARN: Could not find 'name' for the row. Using search term '{field_name}' for dependency scan."
                    )

                print(f"Scanning all cells for dependencies of field '{actual_field_name}'...")
                dependency_pattern = f"${{{actual_field_name}}}"
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
                            # Highlight cleared dependency as modification
                            cell_to_check.set(f"{{{self.namespaces['ss']}}}StyleID", "AIModified")

                cells = row_to_delete.findall(".//ss:Cell", self.namespaces)
                if len(cells) > type_column_index:
                    type_cell = cells[type_column_index]
                    type_data_elem = type_cell.find(".//ss:Data", self.namespaces)
                    if type_data_elem is not None and type_data_elem.text:
                        type_string = type_data_elem.text
                        # Use regex to find and extract the list_name
                        match = re.match(r"^(select_one|select_multiple)\s+(\S+)", actual_field_name)
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
                print(
                    f"Successfully found and removed field with {search_mode} '{field_name}' (actual name: '{actual_field_name}')"
                )
                return True
            else:
                print(f"WARN: Field '{field_name}' not found in survey.")
                return False

        except Exception as e:
            print(f"ERROR in remove_field_by_name: {str(e)}")
            return False

    def modify_field_property(
        self, worksheet_name: str, key_field_name: str, key_field_value: str, property_to_change: str, new_value: str
    ) -> bool:
        """
        Finds a field in a sheet by its key and modifies one of its properties.
        Handles 'settings' sheet as a special case.
        Handles sparse XML rows correctly.
        """
        try:
            self._ensure_highlight_styles()
            worksheet = self.find_worksheet(worksheet_name)
            if worksheet is None:
                print(f"ERROR: {worksheet_name} worksheet not found.")
                return False

            table = self.find_table_in_worksheet(worksheet)
            if table is None:
                print(f"ERROR: Table not found in {worksheet_name} worksheet.")
                return False

            headers = self.get_headers(table)
            try:
                key_col_index = headers.index(key_field_name)
                prop_col_index = headers.index(property_to_change)
            except ValueError:
                print(
                    f"ERROR: Column '{key_field_name}' or '{property_to_change}' not found in {worksheet_name} headers."
                )
                return False

            target_row = None
            rows = table.findall(".//ss:Row", self.namespaces)
            data_rows = rows[1:]  # Skip header

            # SPECIAL CASE FOR SETTINGS
            if worksheet_name == "settings":
                if len(data_rows) > 0:
                    target_row = data_rows[0]  # Get the first data row (index 1 of all_rows)
                else:
                    print(f" WARN: Row not found in '{worksheet_name}'.")
                    return False

            # LOGIC FOR ALL OTHER SHEETS (like 'survey')
            else:
                for row in data_rows:
                    cells = row.findall(".//ss:Cell", self.namespaces)
                    current_idx = 0
                    found_cell = False
                    for cell in cells:
                        index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                        if index_attr:
                            current_idx = int(index_attr) - 1

                        if current_idx == key_col_index:
                            data_elem = cell.find(".//ss:Data", self.namespaces)
                            if data_elem is not None and data_elem.text == key_field_value:
                                target_row = row
                                found_cell = True
                            break  # Stop inner loop

                        current_idx += 1

                    if found_cell:
                        break  # Stop outer loop

            if target_row is None:
                print(f" WARN: Row with {key_field_name} = '{key_field_value}' not found in '{worksheet_name}'.")
                return False

            # --- This point onwards is the same as your file ---
            # Find and update the specific cell for the property
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

                if current_idx > prop_col_index:
                    target_cell = ET.Element(f"{{{self.namespaces['ss']}}}Cell")
                    target_cell.set(f"{{{self.namespaces['ss']}}}Index", str(prop_col_index + 1))
                    target_row.insert(i, target_cell)
                    break

                current_idx += 1

            if target_cell is None:
                # This handles if the cell should be at the end, or if the row was empty
                target_cell = ET.SubElement(target_row, f"{{{self.namespaces['ss']}}}Cell")
                # If it's not the last cell, set its index
                if prop_col_index > current_idx:
                    target_cell.set(f"{{{self.namespaces['ss']}}}Index", str(prop_col_index + 1))

            data_elem = target_cell.find(f".//ss:Data", self.namespaces)
            if data_elem is None:
                data_elem = ET.SubElement(target_cell, f"{{{self.namespaces['ss']}}}Data")

            if str(new_value).upper() == "TRUE":
                data_elem.set(f"{{{self.namespaces['ss']}}}Type", "Boolean")
                data_elem.text = "1"
            elif str(new_value).upper() == "FALSE":
                data_elem.set(f"{{{self.namespaces['ss']}}}Type", "Boolean")
                data_elem.text = "0"
            else:
                data_elem.set(f"{{{self.namespaces['ss']}}}Type", "String")
                data_elem.text = str(new_value)
            # Highlight modified cell
            target_cell.set(f"{{{self.namespaces['ss']}}}StyleID", "AIModified")

            self.modified = True
            print(f" Successfully modified '{property_to_change}' in worksheet '{worksheet_name}'.")
            return True

        except Exception as e:
            print(f"❌ ERROR in modify_field_property: {str(e)}")
            return False

    def clone_and_filter_by_equipment(self, new_form_name: str, equipment_to_keep: List[str]) -> Optional[str]:
        """
        Creates a new, filtered XML file based on a list of equipment types.
        This is a two-pass operation:
        1. Filters the 'survey' sheet and collects all 'list_name's that are still required.
        2. Rebuilds the 'select_one' and 'select_multiple' sheets, keeping only the choice lists collected in pass one.
        """
        try:
            equipment_set_to_keep = {str(e).lower() for e in equipment_to_keep}

            new_root = ET.Element(self.root.tag, self.root.attrib)
            for child in self.root:
                if child.tag != f"{{{self.namespaces['ss']}}}Worksheet":
                    new_root.append(child)

            used_choice_lists = set()

            survey_ws = self.find_worksheet("survey")
            if survey_ws is None:
                raise ValueError("'survey' worksheet not found in master form.")

            survey_table = self.find_table_in_worksheet(survey_ws)
            if survey_table is None:
                raise ValueError("Table not found in master 'survey' worksheet.")

            headers = self.get_headers(survey_table)
            all_rows = survey_table.findall(".//ss:Row", self.namespaces)
            header_row = all_rows[0]
            data_rows = all_rows[1:]

            try:
                type_col_index = headers.index("type")
                equip_col_index = headers.index("equipment_type")
                relevant_col_index = headers.index("relevant")
            except ValueError as e:
                raise ValueError(f"Missing required column in survey: {e}. Headers are: {headers}")

            new_survey_ws = ET.SubElement(new_root, f"{{{self.namespaces['ss']}}}Worksheet")
            new_survey_ws.set(f"{{{self.namespaces['ss']}}}Name", "survey")
            new_survey_table = ET.SubElement(new_survey_ws, f"{{{self.namespaces['ss']}}}Table")
            new_survey_table.append(header_row)

            rows_added_count = 0

            for row in data_rows:
                cells = row.findall(".//ss:Cell", self.namespaces)
                cell_data_map = {}
                current_idx = 0
                for cell in cells:
                    index_attr = cell.get(f"{{{self.namespaces['ss']}}}Index")
                    if index_attr:
                        current_idx = int(index_attr) - 1

                    if current_idx < len(headers):
                        header_name = headers[current_idx]
                        data_elem = cell.find(".//ss:Data", self.namespaces)
                        if data_elem is not None:
                            cell_data_map[header_name] = data_elem.text or ""
                    current_idx += 1

                row_equip_type = cell_data_map.get("equipment_type", "").lower()
                relevant_text = cell_data_map.get("relevant", "").lower()
                row_type_text = cell_data_map.get("type", "")

                keep_this_row = False

                # Match with wildcard support on equipment_type and relevant
                def match_with_wildcards(text: str, pattern: str) -> bool:
                    if pattern is None:
                        return False
                    # direct contains
                    if pattern in text:
                        return True
                    # SQL-like
                    esc = re.escape(pattern)
                    like_pat = "^" + esc.replace("%", ".*").replace("_", ".") + "$"
                    if re.search(like_pat, text, re.IGNORECASE):
                        return True
                    # glob-like
                    import fnmatch as _fnmatch
                    if _fnmatch.fnmatch(text, pattern):
                        return True
                    # regex fallback
                    try:
                        if re.search(pattern, text, re.IGNORECASE):
                            return True
                    except re.error:
                        pass
                    # smart star fallback
                    if "*" in pattern or "%" in pattern or "_" in pattern:
                        star_esc = re.escape(pattern)
                        star_pat = "^" + star_esc.replace("%", ".*").replace("_", ".").replace("\\*", ".*") + "$"
                        return re.search(star_pat, text, re.IGNORECASE) is not None
                    return False

                if not row_equip_type:
                    keep_this_row = True
                else:
                    for equip_name in equipment_set_to_keep:
                        if match_with_wildcards(row_equip_type, equip_name) or match_with_wildcards(relevant_text, equip_name):
                            keep_this_row = True
                            break

                if keep_this_row:
                    new_survey_table.append(row)
                    rows_added_count += 1

                    if row_type_text:
                        match = re.match(r"^(select_one|select_multiple)\s+(\S+)", row_type_text, re.IGNORECASE)
                        if match:
                            list_name = match.group(2)
                            used_choice_lists.add(list_name)

            new_survey_table.set(f"{{{self.namespaces['ss']}}}ExpandedRowCount", str(rows_added_count + 1))
            print(
                f"✅ Survey filtered. Kept {rows_added_count} rows. Found {len(used_choice_lists)} unique choice lists."
            )

            for sheet_name in ["select_one", "select_multiple"]:
                original_choice_ws = self.find_worksheet(sheet_name)
                if original_choice_ws is None:
                    continue

                choice_table = self.find_table_in_worksheet(original_choice_ws)
                if choice_table is None:
                    continue

                choice_headers = self.get_headers(choice_table)
                choice_header_row = choice_table.find(".//ss:Row", self.namespaces)
                all_choice_rows = choice_table.findall(".//ss:Row", self.namespaces)[1:]

                try:
                    list_name_col_index = choice_headers.index("list name")
                except ValueError:
                    print(f"⚠️ WARN: Skipping sheet '{sheet_name}', missing 'list name' column.")
                    continue

                new_choice_ws = ET.SubElement(new_root, f"{{{self.namespaces['ss']}}}Worksheet")
                new_choice_ws.set(f"{{{self.namespaces['ss']}}}Name", sheet_name)
                new_choice_table = ET.SubElement(new_choice_ws, f"{{{self.namespaces['ss']}}}Table")
                new_choice_table.append(choice_header_row)

                choices_added_count = 0
                for row in all_choice_rows:
                    cells = row.findall(".//ss:Cell", self.namespaces)
                    if len(cells) > list_name_col_index:
                        data_elem = cells[list_name_col_index].find(".//ss:Data", self.namespaces)
                        if data_elem is not None and data_elem.text in used_choice_lists:
                            new_choice_table.append(row)
                            choices_added_count += 1

                new_choice_table.set(f"{{{self.namespaces['ss']}}}ExpandedRowCount", str(choices_added_count + 1))
                print(f"✅ Filtered '{sheet_name}' sheet. Kept {choices_added_count} choices.")

            settings_ws = self.find_worksheet("settings")
            if settings_ws is not None:
                new_root.append(settings_ws)

            self.tree = ET.ElementTree(new_root)
            self.modified = True

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Get the original file's directory (just like save_modified_xml)
            original_dir = os.path.dirname(os.path.abspath(self.original_xml_path))
            new_filename = f"modified_{new_form_name.replace(' ', '_')}_{timestamp}.xml"
            output_path = os.path.join(original_dir, new_filename)

            self.tree.write(output_path, encoding="utf-8", xml_declaration=True)
            print(f"✅ Fully Filtered clone (including choices) saved to: {output_path}")
            return output_path

        except Exception as e:
            print(f"❌ ERROR in clone_and_filter: {str(e)}")
            import traceback

            traceback.print_exc()
            return None

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

    def merge_fields_from_source(self, source_xml_path: str, fields_to_copy: List[str]) -> Dict[str, Any]:
        """
        Merges fields (and their choices) from a source XML file into this instance.
        Searches by field name first, then by label (column index 2).
        """
        print(f"Attempting to merge fields: {fields_to_copy}")
        try:
            self._ensure_highlight_styles()

            source_tree = ET.parse(source_xml_path)
            source_root = source_tree.getroot()

            # --- Find Source Survey ---
            source_survey_ws = None
            for ws in source_root.findall(".//ss:Worksheet", self.namespaces):
                if ws.get(f"{{{self.namespaces['ss']}}}Name") == "survey":
                    source_survey_ws = ws
                    break
            if source_survey_ws is None:
                # Note: The original code had a bug here, finding self.find_worksheet("survey") first.
                # This corrected version only searches the source_root.
                return {"success": False, "error": "Source survey worksheet not found"}

            source_table = self.find_table_in_worksheet(source_survey_ws)
            if source_table is None:
                return {"success": False, "error": "Source survey table not found"}

            source_headers = self.get_headers(source_table)
            try:
                source_name_idx = source_headers.index("name")
                source_type_idx = source_headers.index("type")
                source_label_idx = 2  # As per original logic
            except ValueError:
                return {"success": False, "error": "'name' or 'type' not found in source headers."}

            # --- Find Destination Survey ---
            dest_survey_ws = self.find_worksheet("survey")
            if dest_survey_ws is None:
                return {"success": False, "error": "Destination survey worksheet not found"}
            dest_table = self.find_table_in_worksheet(dest_survey_ws)
            if dest_table is None:
                return {"success": False, "error": "Destination survey table not found"}

            rows_to_copy = []
            used_choice_lists = set()
            source_rows = source_table.findall(".//ss:Row", self.namespaces)[1:]  # Skip header

            # --- Pass 1: Find all survey rows to copy ---
            for field_name in fields_to_copy:
                found_row = None

                # Search by name
                for row in source_rows:
                    cells = row.findall(".//ss:Cell", self.namespaces)
                    current_idx = 0
                    for cell in cells:
                        if cell.get(f"{{{self.namespaces['ss']}}}Index"):
                            current_idx = int(cell.get(f"{{{self.namespaces['ss']}}}Index")) - 1
                        if current_idx == source_name_idx:
                            data = cell.find(".//ss:Data", self.namespaces)
                            if data is not None and data.text == field_name:
                                found_row = row
                                break
                        current_idx += 1
                    if found_row:
                        break

                # Search by label (fallback)
                if found_row is None:
                    for row in source_rows:
                        cells = row.findall(".//ss:Cell", self.namespaces)
                        current_idx = 0
                        for cell in cells:
                            if cell.get(f"{{{self.namespaces['ss']}}}Index"):
                                current_idx = int(cell.get(f"{{{self.namespaces['ss']}}}Index")) - 1
                            if current_idx == source_label_idx:
                                data = cell.find(".//ss:Data", self.namespaces)
                                if data is not None and data.text and field_name in data.text:
                                    found_row = row
                                    break
                            current_idx += 1
                        if found_row:
                            break

                # If found, add to list and check for choices
                if found_row:
                    rows_to_copy.append(found_row)
                    cells = found_row.findall(".//ss:Cell", self.namespaces)
                    current_idx = 0
                    for cell in cells:
                        if cell.get(f"{{{self.namespaces['ss']}}}Index"):
                            current_idx = int(cell.get(f"{{{self.namespaces['ss']}}}Index")) - 1
                        if current_idx == source_type_idx:
                            data = cell.find(".//ss:Data", self.namespaces)
                            if data is not None and data.text:
                                match = re.match(r"^(select_one|select_multiple)\s+(\S+)", data.text)
                                if match:
                                    used_choice_lists.add(match.group(2))
                            break
                        current_idx += 1

            # --- Pass 2: Copy survey rows (with fixes) ---
            style_id_key = f"{{{self.namespaces['ss']}}}StyleID"
            for row in rows_to_copy:
                # FIX 1: Strip StyleID from all cells in the row
                for cell in row.findall(".//ss:Cell", self.namespaces):
                    if style_id_key in cell.attrib:
                        del cell.attrib[style_id_key]

                dest_table.append(row)
                # Mark copied row as AI-added for visibility
                row.set(style_id_key, "AIAdded")
                self.modified = True

            print(f"✅ Copied {len(rows_to_copy)} fields to survey.")

            # FIX 2: Update ExpandedRowCount for survey table
            # We count all rows (including header)
            new_survey_row_count = len(dest_table.findall(".//ss:Row", self.namespaces))
            dest_table.set(f"{{{self.namespaces['ss']}}}ExpandedRowCount", str(new_survey_row_count))
            print(f"✅ Updated survey ExpandedRowCount to {new_survey_row_count}.")

            # --- Pass 3: Copy choice rows (with fixes) ---
            choices_copied_count = 0
            if used_choice_lists:
                for sheet_name in ["select_one", "select_multiple"]:
                    source_choice_ws = None
                    for ws in source_root.findall(".//ss:Worksheet", self.namespaces):
                        if ws.get(f"{{{self.namespaces['ss']}}}Name") == sheet_name:
                            source_choice_ws = ws
                            break

                    dest_choice_ws = self.find_worksheet(sheet_name)
                    if source_choice_ws is None or dest_choice_ws is None:
                        continue

                    source_choice_table = self.find_table_in_worksheet(source_choice_ws)
                    dest_choice_table = self.find_table_in_worksheet(dest_choice_ws)
                    if source_choice_table is None or dest_choice_table is None:
                        continue

                    try:
                        source_choice_headers = self.get_headers(source_choice_table)
                        list_name_idx = source_choice_headers.index("list name")
                    except ValueError:
                        continue  # Skip sheet if no 'list name' header

                    # Find and append all matching choice rows
                    for row in source_choice_table.findall(".//ss:Row", self.namespaces)[1:]:
                        cells = row.findall(".//ss:Cell", self.namespaces)
                        current_idx = 0
                        for cell in cells:
                            if cell.get(f"{{{self.namespaces['ss']}}}Index"):
                                current_idx = int(cell.get(f"{{{self.namespaces['ss']}}}Index")) - 1

                            if current_idx == list_name_idx:
                                data = cell.find(".//ss:Data", self.namespaces)
                                if data is not None and data.text in used_choice_lists:
                                    # FIX 1: Strip StyleID from all cells in the choice row
                                    for choice_cell in row.findall(".//ss:Cell", self.namespaces):
                                        if style_id_key in choice_cell.attrib:
                                            del choice_cell.attrib[style_id_key]

                                    dest_choice_table.append(row)
                                    # Mark copied choice row as AI-added
                                    row.set(style_id_key, "AIAdded")
                                    choices_copied_count += 1
                                    self.modified = True
                                break  # Move to next row
                            current_idx += 1

                    # FIX 2: Update ExpandedRowCount for this choice table
                    # We count all rows (including header)
                    new_choice_row_count = len(dest_choice_table.findall(".//ss:Row", self.namespaces))
                    dest_choice_table.set(f"{{{self.namespaces['ss']}}}ExpandedRowCount", str(new_choice_row_count))
                    print(f"✅ Updated {sheet_name} ExpandedRowCount to {new_choice_row_count}.")

            print(f"✅ Copied {choices_copied_count} choices.")
            return {
                "success": True,
                "fields_copied_count": len(rows_to_copy),
                "choices_copied_count": choices_copied_count,
            }
        except Exception as e:
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def merge_by_filter_from_source(self, source_xml_path: str, filter_groups: List[List[Dict[str, str]]]) -> Dict[str, Any]:
        """Merge rows from source survey into destination based on filters across any columns.

        filter_groups: OR-of-ANDs where each condition has keys: property, operator, value
        Operators: equals, contains, starts_with, ends_with, like, glob, regex
        """
        try:
            self._ensure_highlight_styles()

            source_tree = ET.parse(source_xml_path)
            source_root = source_tree.getroot()

            # Locate tables
            source_survey_ws = None
            for ws in source_root.findall(".//ss:Worksheet", self.namespaces):
                if ws.get(f"{{{self.namespaces['ss']}}}Name") == "survey":
                    source_survey_ws = ws
                    break
            if source_survey_ws is None:
                return {"success": False, "error": "Source survey worksheet not found"}
            source_table = self.find_table_in_worksheet(source_survey_ws)
            if source_table is None:
                return {"success": False, "error": "Source survey table not found"}

            dest_survey_ws = self.find_worksheet("survey")
            if dest_survey_ws is None:
                return {"success": False, "error": "Destination survey worksheet not found"}
            dest_table = self.find_table_in_worksheet(dest_survey_ws)
            if dest_table is None:
                return {"success": False, "error": "Destination survey table not found"}

            headers = self.get_headers(source_table)
            source_rows = source_table.findall(".//ss:Row", self.namespaces)[1:]

            def condition_matches(cell_value: str, op: str, val: str) -> bool:
                s = str(cell_value or "")
                v = str(val or "")
                s_l, v_l = s.lower(), v.lower()
                if op == "equals":
                    return s_l == v_l
                if op == "contains":
                    return v_l in s_l
                if op == "starts_with":
                    return s_l.startswith(v_l)
                if op == "ends_with":
                    return s_l.endswith(v_l)
                if op == "like":
                    escaped = re.escape(v)
                    pattern = "^" + escaped.replace("%", ".*").replace("_", ".") + "$"
                    return re.search(pattern, s, re.IGNORECASE) is not None
                if op == "glob":
                    import fnmatch as _fnmatch
                    return _fnmatch.fnmatch(s, v)
                if op == "regex":
                    try:
                        return re.search(v, s, re.IGNORECASE) is not None
                    except re.error:
                        return False
                if any(ch in v for ch in ["*", "%", "_"]):
                    escaped = re.escape(v)
                    pattern = "^" + escaped.replace("%", ".*").replace("_", ".").replace("\\*", ".*") + "$"
                    return re.search(pattern, s, re.IGNORECASE) is not None
                return s_l == v_l

            def row_matches(row: ET.Element) -> bool:
                row_data: Dict[str, str] = {}
                cells = row.findall(".//ss:Cell", self.namespaces)
                current_idx = 0
                for cell in cells:
                    idx = cell.get(f"{{{self.namespaces['ss']}}}Index")
                    if idx:
                        current_idx = int(idx) - 1
                    if current_idx < len(headers):
                        header_name = headers[current_idx]
                        data_elem = cell.find(".//ss:Data", self.namespaces)
                        if data_elem is not None:
                            row_data[header_name] = data_elem.text or ""
                    current_idx += 1

                for group in filter_groups or []:
                    ok = True
                    for cond in group:
                        if not condition_matches(row_data.get(cond.get("property", ""), ""), cond.get("operator", "equals"), cond.get("value", "")):
                            ok = False
                            break
                    if ok:
                        return True
                return False

            rows_to_copy: List[ET.Element] = []
            used_choice_lists: set[str] = set()
            try:
                type_idx = headers.index("type")
            except ValueError:
                type_idx = None

            for row in source_rows:
                if row_matches(row):
                    cloned = ET.fromstring(ET.tostring(row))
                    style_attr = f"{{{self.namespaces['ss']}}}StyleID"
                    if style_attr in cloned.attrib:
                        del cloned.attrib[style_attr]
                    for c in cloned.findall(".//ss:Cell", self.namespaces):
                        if style_attr in c.attrib:
                            del c.attrib[style_attr]
                        c.set(style_attr, "AIMerged")
                    # detect select list name
                    if type_idx is not None:
                        current_idx = 0
                        for cell in row.findall(".//ss:Cell", self.namespaces):
                            idx = cell.get(f"{{{self.namespaces['ss']}}}Index")
                            if idx:
                                current_idx = int(idx) - 1
                            if current_idx == type_idx:
                                data = cell.find(".//ss:Data", self.namespaces)
                                if data is not None and data.text:
                                    m = re.match(r"^(select_one|select_multiple)\s+(\S+)", data.text)
                                    if m:
                                        used_choice_lists.add(m.group(2))
                                break
                            current_idx += 1
                    rows_to_copy.append(cloned)

            for r in rows_to_copy:
                dest_table.append(r)
                self.modified = True
            dest_table.set(f"{{{self.namespaces['ss']}}}ExpandedRowCount", str(len(dest_table.findall(".//ss:Row", self.namespaces))))

            # Copy choices
            choices_copied = 0
            if used_choice_lists:
                for sheet_name in ["select_one", "select_multiple"]:
                    source_choice_ws = None
                    for ws in source_root.findall(".//ss:Worksheet", self.namespaces):
                        if ws.get(f"{{{self.namespaces['ss']}}}Name") == sheet_name:
                            source_choice_ws = ws
                            break
                    dest_choice_ws = self.find_worksheet(sheet_name)
                    if source_choice_ws is None or dest_choice_ws is None:
                        continue
                    source_choice_table = self.find_table_in_worksheet(source_choice_ws)
                    dest_choice_table = self.find_table_in_worksheet(dest_choice_ws)
                    if source_choice_table is None or dest_choice_table is None:
                        continue
                    sh = self.get_headers(source_choice_table)
                    try:
                        ln_idx = sh.index("list name")
                    except ValueError:
                        continue
                    style_attr = f"{{{self.namespaces['ss']}}}StyleID"
                    for row in source_choice_table.findall(".//ss:Row", self.namespaces)[1:]:
                        current_idx = 0
                        for cell in row.findall(".//ss:Cell", self.namespaces):
                            idx = cell.get(f"{{{self.namespaces['ss']}}}Index")
                            if idx:
                                current_idx = int(idx) - 1
                            if current_idx == ln_idx:
                                data = cell.find(".//ss:Data", self.namespaces)
                                if data is not None and data.text in used_choice_lists:
                                    cloned = ET.fromstring(ET.tostring(row))
                                    for c in cloned.findall(".//ss:Cell", self.namespaces):
                                        if style_attr in c.attrib:
                                            del c.attrib[style_attr]
                                        c.set(style_attr, "AIMerged")
                                    dest_choice_table.append(cloned)
                                    choices_copied += 1
                                    break
                            current_idx += 1
                    dest_choice_table.set(f"{{{self.namespaces['ss']}}}ExpandedRowCount", str(len(dest_choice_table.findall(".//ss:Row", self.namespaces))))

            return {"success": True, "merged_rows": len(rows_to_copy), "copied_choices": choices_copied, "modified": self.modified}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

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
def create_xml_editor(xml_file_path: str, base_original_path: str = None) -> XLSFormXMLEditor:
    """Create an XML editor instance"""
    return XLSFormXMLEditor(xml_file_path, base_original_path=base_original_path)
