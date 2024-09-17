import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
import os
import hashlib
from difflib import SequenceMatcher

def unmerge_cells(worksheet):
    merged_ranges = list(worksheet.merged_cells.ranges)
    for merged_range in merged_ranges:
        worksheet.unmerge_cells(str(merged_range))
        value = worksheet.cell(merged_range.min_row, merged_range.min_col).value
        for row in range(merged_range.min_row, merged_range.max_row + 1):
            for col in range(merged_range.min_col, merged_range.max_col + 1):
                worksheet.cell(row, col, value)

def get_function_details(core_ocir_sheet):
    function_details = {}
    for row in core_ocir_sheet.iter_rows(min_row=2, values_only=True):
        if row[0]:  # Function ID
            function_details[row[0]] = {'name': row[1], 'owner': row[3]}
    return function_details

def create_hash(values):
    return hashlib.md5(''.join(str(v) for v in values if pd.notna(v)).encode()).hexdigest()

def compare_strings(s1, s2):
    ratio = SequenceMatcher(None, str(s1), str(s2)).ratio()
    if ratio == 1:
        return 'No change'
    elif ratio > 0.8:
        return 'Minor change'
    elif ratio > 0.5:
        return 'Major change'
    else:
        return 'Complete change'

def compare_excel_files(file1_path, file2_path, output_path):
    wb1 = openpyxl.load_workbook(file1_path, data_only=True)
    wb2 = openpyxl.load_workbook(file2_path, data_only=True)
    wb_output = openpyxl.Workbook()
    ws_output = wb_output.active
    ws_output.title = 'Comparison'

    colors = {
        'Cell value added': 'C6EFCE',
        'Cell value deleted': 'FFC7CE',
        'Minor change': 'FFEB9C',
        'Major change': 'FFD966',
        'Complete change': 'F4B084',
        'Cell value moved': 'D9E1F2'
    }

    # Set up header
    headers = ['Sr. No', 'Function Name', 'Owner', 'Sheet Name', 
               os.path.splitext(os.path.basename(file1_path))[0] + ' Cell',
               os.path.splitext(os.path.basename(file1_path))[0] + ' Value',
               os.path.splitext(os.path.basename(file2_path))[0] + ' Cell',
               os.path.splitext(os.path.basename(file2_path))[0] + ' Value',
               'Change Summary']
    ws_output.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws_output.cell(row=1, column=col)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center')

    row_num = 0

    for sheet_name in wb1.sheetnames:
        ws1 = wb1[sheet_name]
        unmerge_cells(ws1)
        
        if sheet_name in wb2.sheetnames:
            ws2 = wb2[sheet_name]
            unmerge_cells(ws2)

            df1 = pd.DataFrame(ws1.values)
            df2 = pd.DataFrame(ws2.values)

            # Compare cells column by column
            for col in range(df1.shape[1]):
                processed_rows = set()

                for row1 in range(df1.shape[0]):
                    if pd.isna(df1.iloc[row1, col]):
                        continue

                    # Create context hash using non-changed values in previous columns
                    context_hash1 = create_hash([df1.iloc[row1, i] for i in range(col) if i not in processed_rows])
                    
                    found_match = False
                    for row2 in range(df2.shape[0]):
                        if row2 in processed_rows:
                            continue

                        context_hash2 = create_hash([df2.iloc[row2, i] for i in range(col) if i not in processed_rows])

                        if context_hash1 == context_hash2:
                            # Compare values
                            value1 = df1.iloc[row1, col]
                            value2 = df2.iloc[row2, col]
                            change_type = compare_strings(value1, value2)

                            if change_type != 'No change':
                                row_num += 1
                                function_id = df1.iloc[row1, 0]
                                function_name = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('name', '')
                                owner = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('owner', '')
                                ws_output.append([row_num, function_name, owner, sheet_name, 
                                                  f'{get_column_letter(col+1)}{row1+1}', value1,
                                                  f'{get_column_letter(col+1)}{row2+1}', value2,
                                                  change_type])
                                for c in range(1, 10):
                                    ws_output.cell(row=row_num+1, column=c).fill = PatternFill(start_color=colors[change_type], end_color=colors[change_type], fill_type='solid')

                            processed_rows.add(row2)
                            found_match = True
                            break

                    if not found_match:
                        # Cell deleted
                        row_num += 1
                        function_id = df1.iloc[row1, 0]
                        function_name = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('name', '')
                        owner = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('owner', '')
                        ws_output.append([row_num, function_name, owner, sheet_name, 
                                          f'{get_column_letter(col+1)}{row1+1}', df1.iloc[row1, col],
                                          '', '', 'Cell value deleted'])
                        for c in range(1, 10):
                            ws_output.cell(row=row_num+1, column=c).fill = PatternFill(start_color=colors['Cell value deleted'], end_color=colors['Cell value deleted'], fill_type='solid')

                # Check for added cells in this column
                for row2 in range(df2.shape[0]):
                    if row2 not in processed_rows and not pd.isna(df2.iloc[row2, col]):
                        row_num += 1
                        function_id = df2.iloc[row2, 0]
                        function_name = get_function_details(wb2['Core OCIR Data']).get(function_id, {}).get('name', '')
                        owner = get_function_details(wb2['Core OCIR Data']).get(function_id, {}).get('owner', '')
                        ws_output.append([row_num, function_name, owner, sheet_name, 
                                          '', '',
                                          f'{get_column_letter(col+1)}{row2+1}', df2.iloc[row2, col],
                                          'Cell value added'])
                        for c in range(1, 10):
                            ws_output.cell(row=row_num+1, column=c).fill = PatternFill(start_color=colors['Cell value added'], end_color=colors['Cell value added'], fill_type='solid')

    # Add color legends
    ws_output['K2'] = 'Color Legend'
    ws_output['K2'].font = Font(bold=True)
    for i, (change_type, color) in enumerate(colors.items(), start=3):
        cell = ws_output.cell(row=i, column=11, value=change_type)
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')

    # Adjust column widths
    for col in ws_output.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = (max_length + 2)
        ws_output.column_dimensions[column].width = adjusted_width

    wb_output.save(output_path)

# Usage
file1_path = 'path/to/old_file.xlsx'
file2_path = 'path/to/new_file.xlsx'
output_path = 'path/to/output.xlsx'
compare_excel_files(file1_path, file2_path, output_path)