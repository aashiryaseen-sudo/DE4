import xml.etree.ElementTree as ET
import json
from typing import List, Dict, Any, Optional

class XLSFormParser:
    def __init__(self, xml_file_path: str):
        self.xml_file_path = xml_file_path
        self.namespaces = {
            'ss': 'urn:schemas-microsoft-com:office:spreadsheet',
            'o': 'urn:schemas-microsoft-com:office:office',
            'x': 'urn:schemas-microsoft-com:office:excel',
            'html': 'http://www.w3.org/TR/REC-html40'
        }
    
    def get_tree(self):
        """Get the parsed XML tree"""
        return ET.parse(self.xml_file_path)
        
    def parse_survey_fields(self) -> List[Dict[str, Any]]:
        """Parse the survey worksheet and extract field data"""
        tree = ET.parse(self.xml_file_path)
        root = tree.getroot()
        
        # Find the survey worksheet
        survey_worksheet = None
        for worksheet in root.findall('.//ss:Worksheet', self.namespaces):
            name_attr = worksheet.get('{urn:schemas-microsoft-com:office:spreadsheet}Name')
            if name_attr == 'survey':
                survey_worksheet = worksheet
                break
        
        if not survey_worksheet:
            raise ValueError("Survey worksheet not found")
        
        # Get the table data
        table = survey_worksheet.find('.//ss:Table', self.namespaces)
        if not table:
            raise ValueError("Table not found in survey worksheet")
        
        rows = table.findall('.//ss:Row', self.namespaces)
        if len(rows) < 2:
            raise ValueError("Not enough rows found")
        
        # Extract headers from first row
        headers = []
        header_row = rows[0]
        for cell in header_row.findall('.//ss:Cell', self.namespaces):
            data_elem = cell.find('.//ss:Data', self.namespaces)
            if data_elem is not None and data_elem.text:
                headers.append(data_elem.text)
            else:
                headers.append("")
        
        # Extract data from remaining rows
        fields_data = []
        for row in rows[1:]:
            cells = row.findall('.//ss:Cell', self.namespaces)
            if not cells:
                continue
                
            row_data = {}
            cell_index = 0
            
            for i, cell in enumerate(cells):
                # Handle cell index attribute for sparse data
                index_attr = cell.get('{urn:schemas-microsoft-com:office:spreadsheet}Index')
                if index_attr:
                    cell_index = int(index_attr) - 1
                
                # Get cell data
                data_elem = cell.find('.//ss:Data', self.namespaces)
                value = data_elem.text if data_elem is not None else ""
                
                # Map to header if we have one
                if cell_index < len(headers) and headers[cell_index]:
                    row_data[headers[cell_index]] = value
                
                cell_index += 1
            
            # Only add rows that have meaningful data (at least a name or type)
            if row_data.get('name') or row_data.get('type'):
                fields_data.append(row_data)
        
        return fields_data
    
    def parse_choices(self, worksheet_name: str) -> List[Dict[str, Any]]:
        """Parse choices from select_one or select_multiple worksheet"""
        tree = ET.parse(self.xml_file_path)
        root = tree.getroot()
        
        # Find the specified worksheet
        target_worksheet = None
        for worksheet in root.findall('.//ss:Worksheet', self.namespaces):
            name_attr = worksheet.get('{urn:schemas-microsoft-com:office:spreadsheet}Name')
            if name_attr == worksheet_name:
                target_worksheet = worksheet
                break
        
        if not target_worksheet:
            return []
        
        # Get the table data
        table = target_worksheet.find('.//ss:Table', self.namespaces)
        if not table:
            return []
        
        rows = table.findall('.//ss:Row', self.namespaces)
        if len(rows) < 2:
            return []
        
        # Extract headers from first row
        headers = []
        header_row = rows[0]
        for cell in header_row.findall('.//ss:Cell', self.namespaces):
            data_elem = cell.find('.//ss:Data', self.namespaces)
            if data_elem is not None and data_elem.text:
                headers.append(data_elem.text)
            else:
                headers.append("")
        
        # Extract choice data from remaining rows
        choices_data = []
        for row in rows[1:]:
            cells = row.findall('.//ss:Cell', self.namespaces)
            if not cells:
                continue
                
            row_data = {}
            cell_index = 0
            
            for i, cell in enumerate(cells):
                # Handle cell index attribute for sparse data
                index_attr = cell.get('{urn:schemas-microsoft-com:office:spreadsheet}Index')
                if index_attr:
                    cell_index = int(index_attr) - 1
                
                # Get cell data
                data_elem = cell.find('.//ss:Data', self.namespaces)
                value = data_elem.text if data_elem is not None else ""
                
                # Map to header if we have one
                if cell_index < len(headers) and headers[cell_index]:
                    row_data[headers[cell_index]] = value
                
                cell_index += 1
            
            # Only add rows that have meaningful data
            if row_data.get('label') or row_data.get('name'):
                choices_data.append(row_data)
        
        return choices_data
    
    def parse_settings(self) -> Dict[str, Any]:
        """Parse form settings from the settings worksheet"""
        tree = ET.parse(self.xml_file_path)
        root = tree.getroot()
        
        # Find the settings worksheet
        settings_worksheet = None
        for worksheet in root.findall('.//ss:Worksheet', self.namespaces):
            name_attr = worksheet.get('{urn:schemas-microsoft-com:office:spreadsheet}Name')
            if name_attr == 'settings':
                settings_worksheet = worksheet
                break
        
        if not settings_worksheet:
            return {}
        
        # Get the table data
        table = settings_worksheet.find('.//ss:Table', self.namespaces)
        if not table:
            return {}
        
        rows = table.findall('.//ss:Row', self.namespaces)
        if len(rows) < 2:
            return {}
        
        # Extract headers and values
        headers = []
        values = []
        
        # Get headers from first row
        header_row = rows[0]
        for cell in header_row.findall('.//ss:Cell', self.namespaces):
            data_elem = cell.find('.//ss:Data', self.namespaces)
            if data_elem is not None and data_elem.text:
                headers.append(data_elem.text)
            else:
                headers.append("")
        
        # Get values from second row
        value_row = rows[1]
        for cell in value_row.findall('.//ss:Cell', self.namespaces):
            data_elem = cell.find('.//ss:Data', self.namespaces)
            if data_elem is not None:
                if data_elem.get('{urn:schemas-microsoft-com:office:spreadsheet}Type') == 'Number':
                    try:
                        values.append(int(data_elem.text))
                    except:
                        values.append(data_elem.text)
                elif data_elem.get('{urn:schemas-microsoft-com:office:spreadsheet}Type') == 'Boolean':
                    values.append(data_elem.text == '1')
                else:
                    values.append(data_elem.text if data_elem.text else "")
            else:
                values.append("")
        
        # Combine headers and values into a dictionary
        settings = {}
        for i, header in enumerate(headers):
            if header and i < len(values):
                settings[header] = values[i]
        
        return settings
    
    def discover_worksheets(self) -> List[str]:
        """Dynamically discover all worksheet names in the XML file"""
        tree = ET.parse(self.xml_file_path)
        root = tree.getroot()
        
        worksheet_names = []
        for worksheet in root.findall('.//ss:Worksheet', self.namespaces):
            name_attr = worksheet.get('{urn:schemas-microsoft-com:office:spreadsheet}Name')
            if name_attr:
                worksheet_names.append(name_attr)
        
        return worksheet_names
    
    def parse_worksheet_generic(self, worksheet_name: str) -> Dict[str, Any]:
        """Generic parser for any worksheet - returns structure and data"""
        tree = ET.parse(self.xml_file_path)
        root = tree.getroot()
        
        # Find the worksheet
        target_worksheet = None
        for worksheet in root.findall('.//ss:Worksheet', self.namespaces):
            name_attr = worksheet.get('{urn:schemas-microsoft-com:office:spreadsheet}Name')
            if name_attr == worksheet_name:
                target_worksheet = worksheet
                break
        
        if target_worksheet is None:
            return {
                'worksheet_name': worksheet_name,
                'exists': False,
                'error': 'Worksheet not found'
            }
        
        # Get the table data
        table = target_worksheet.find('.//ss:Table', self.namespaces)
        if table is None:
            return {
                'worksheet_name': worksheet_name,
                'exists': True,
                'has_data': False,
                'error': 'No table found in worksheet'
            }
        
        # Get table dimensions
        expanded_rows = table.get('{urn:schemas-microsoft-com:office:spreadsheet}ExpandedRowCount', '0')
        expanded_cols = table.get('{urn:schemas-microsoft-com:office:spreadsheet}ExpandedColumnCount', '0')
        
        rows = table.findall('.//ss:Row', self.namespaces)
        
        result = {
            'worksheet_name': worksheet_name,
            'exists': True,
            'has_data': True,
            'dimensions': {
                'total_rows': int(expanded_rows),
                'total_columns': int(expanded_cols),
                'actual_rows_with_data': len(rows)
            },
            'headers': [],
            'sample_data': [],
            'data_types': {},
            'column_info': []
        }
        
        if len(rows) < 1:
            result['has_data'] = False
            result['error'] = 'No rows found'
            return result
        
        # Extract headers from first row
        headers = []
        header_row = rows[0]
        header_cells = header_row.findall('.//ss:Cell', self.namespaces)
        
        for i, cell in enumerate(header_cells):
            # Handle cell index for sparse data
            cell_index = i
            index_attr = cell.get('{urn:schemas-microsoft-com:office:spreadsheet}Index')
            if index_attr:
                cell_index = int(index_attr) - 1
            
            data_elem = cell.find('.//ss:Data', self.namespaces)
            header_text = data_elem.text if data_elem is not None and data_elem.text else f"Column_{cell_index + 1}"
            
            # Pad headers list if needed
            while len(headers) <= cell_index:
                headers.append(f"Column_{len(headers) + 1}")
            
            headers[cell_index] = header_text
        
        result['headers'] = headers
        
        # Analyze first few data rows (excluding header)
        sample_rows = []
        data_type_analysis = {}
        
        for row_idx, row in enumerate(rows[1:11], 1):  # Get up to 10 sample rows
            cells = row.findall('.//ss:Cell', self.namespaces)
            row_data = {}
            
            for i, cell in enumerate(cells):
                cell_index = i
                index_attr = cell.get('{urn:schemas-microsoft-com:office:spreadsheet}Index')
                if index_attr:
                    cell_index = int(index_attr) - 1
                
                data_elem = cell.find('.//ss:Data', self.namespaces)
                if data_elem is not None:
                    data_type = data_elem.get('{urn:schemas-microsoft-com:office:spreadsheet}Type', 'String')
                    value = data_elem.text if data_elem.text else ""
                else:
                    data_type = 'Empty'
                    value = ""
                
                # Map to header
                if cell_index < len(headers):
                    column_name = headers[cell_index]
                    row_data[column_name] = {
                        'value': value,
                        'type': data_type
                    }
                    
                    # Track data types
                    if column_name not in data_type_analysis:
                        data_type_analysis[column_name] = {}
                    if data_type not in data_type_analysis[column_name]:
                        data_type_analysis[column_name][data_type] = 0
                    data_type_analysis[column_name][data_type] += 1
            
            if row_data:  # Only add non-empty rows
                sample_rows.append({
                    'row_number': row_idx,
                    'data': row_data
                })
        
        result['sample_data'] = sample_rows
        result['data_types'] = data_type_analysis
        
        # Create column info summary
        column_info = []
        for col_name in headers:
            col_info = {
                'name': col_name,
                'data_types': data_type_analysis.get(col_name, {}),
                'has_data': col_name in data_type_analysis
            }
            column_info.append(col_info)
        
        result['column_info'] = column_info
        
        return result
    
    def analyze_complete_form(self) -> Dict[str, Any]:
        """Analyze the complete XLSForm dynamically"""
        worksheets = self.discover_worksheets()
        
        form_analysis = {
            'file_name': self.xml_file_path,
            'total_worksheets': len(worksheets),
            'worksheet_names': worksheets,
            'worksheets': {}
        }
        
        # Analyze each worksheet
        for ws_name in worksheets:
            form_analysis['worksheets'][ws_name] = self.parse_worksheet_generic(ws_name)
        
        # Add summary statistics
        total_rows = 0
        total_columns = 0
        worksheets_with_data = 0
        
        for ws_name, ws_data in form_analysis['worksheets'].items():
            if ws_data.get('has_data', False):
                worksheets_with_data += 1
                total_rows += ws_data['dimensions']['actual_rows_with_data']
                total_columns += len(ws_data.get('headers', []))
        
        form_analysis['summary'] = {
            'worksheets_with_data': worksheets_with_data,
            'total_data_rows': total_rows,
            'total_columns_across_sheets': total_columns,
            'is_xlsform': 'survey' in [ws.lower() for ws in worksheets]
        }
        
        return form_analysis
    
    def parse_all_data(self) -> Dict[str, Any]:
        """Parse all data from the XLSForm (backward compatibility)"""
        return {
            'survey': self.parse_survey_fields(),
            'select_one': self.parse_choices('select_one'),
            'select_multiple': self.parse_choices('select_multiple'),
            'settings': self.parse_settings()
        }
    
    def get_field_summary(self) -> Dict[str, Any]:
        """Get a summary of the parsed fields"""
        fields = self.parse_survey_fields()
        
        # Count different field types
        type_counts = {}
        for field in fields:
            field_type = field.get('type', 'unknown')
            type_counts[field_type] = type_counts.get(field_type, 0) + 1
        
        return {
            'total_fields': len(fields),
            'type_counts': type_counts,
            'sample_fields': fields[:5]  # First 5 fields as sample
        }

if __name__ == "__main__":
    parser = XLSFormParser("EMCOR-ABC PM 2025v1.0-PV.xml")
    
    try:
        # Get summary first
        summary = parser.get_field_summary()
        print("Field Summary:")
        print(f"Total fields: {summary['total_fields']}")
        print("\nField types:")
        for field_type, count in summary['type_counts'].items():
            print(f"  {field_type}: {count}")
        
        print("\nSample fields:")
        for i, field in enumerate(summary['sample_fields'], 1):
            print(f"{i}. Name: {field.get('name', 'N/A')}, Type: {field.get('type', 'N/A')}")
            if 'label' in field and field['label']:
                print(f"   Label: {field['label'][:100]}...")
        
        # Parse all data and save to separate JSON files
        all_data = parser.parse_all_data()
        
        # Save survey fields
        with open('survey_fields.json', 'w', encoding='utf-8') as f:
            json.dump(all_data['survey'], f, indent=2, ensure_ascii=False)
        
        # Save choices
        with open('select_one_choices.json', 'w', encoding='utf-8') as f:
            json.dump(all_data['select_one'], f, indent=2, ensure_ascii=False)
        
        with open('select_multiple_choices.json', 'w', encoding='utf-8') as f:
            json.dump(all_data['select_multiple'], f, indent=2, ensure_ascii=False)
        
        # Save settings
        with open('form_settings.json', 'w', encoding='utf-8') as f:
            json.dump(all_data['settings'], f, indent=2, ensure_ascii=False)
        
        print(f"\nAll data saved to JSON files:")
        print(f"- Survey fields: {len(all_data['survey'])} fields")
        print(f"- Select one choices: {len(all_data['select_one'])} choices")
        print(f"- Select multiple choices: {len(all_data['select_multiple'])} choices")
        print(f"- Form settings: {len(all_data['settings'])} settings")
        
    except Exception as e:
        print(f"Error parsing XML: {e}")
