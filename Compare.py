import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
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
    return hashlib.md5(''.join(str(v) for v in values if pd.notna(v) and v != '').encode()).hexdigest()

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

def get_last_column(sheet):
    for col in range(1, sheet.max_column + 1):
        if sheet.cell(row=1, column=col).value is None or sheet.cell(row=1, column=col).value == '':
            return col - 1
    return sheet.max_column

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
        'Cell value moved': 'D9E1F2',
        'Structure mismatch': 'FF0000'
    }

    source1_name = os.path.splitext(os.path.basename(file1_path))[0].split(' - ')[-1]
    source2_name = os.path.splitext(os.path.basename(file2_path))[0].split(' - ')[-1]

    # Set up header
    headers = ['Sr. No', 'Function Name', 'Owner', 'Sheet Name', 
               f'{source1_name} Source Cell', f'{source1_name} Cell Value',
               f'{source2_name} Source Cell', f'{source2_name} Cell Value',
               'Change Summary']
    ws_output.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws_output.cell(row=1, column=col)
        cell.font = Font(bold=True, color='000000')
        cell.fill = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center')

    row_num = 0

    # Check if both files have the same sheets
    if set(wb1.sheetnames) != set(wb2.sheetnames):
        row_num += 1
        ws_output.append([row_num, '', '', '', '', '', '', '', 'Sheet structure mismatch'])
        for col in range(1, 10):
            ws_output.cell(row=row_num+1, column=col).fill = PatternFill(start_color=colors['Structure mismatch'], end_color=colors['Structure mismatch'], fill_type='solid')

    function_details = get_function_details(wb1['Core OCIR Data'])

    for sheet_name in wb1.sheetnames:
        if sheet_name not in wb2.sheetnames:
            continue

        ws1 = wb1[sheet_name]
        ws2 = wb2[sheet_name]

        unmerge_cells(ws1)
        unmerge_cells(ws2)

        last_col1 = get_last_column(ws1)
        last_col2 = get_last_column(ws2)

        if last_col1 != last_col2:
            row_num += 1
            ws_output.append([row_num, '', '', sheet_name, '', '', '', '', f'Column count mismatch: {last_col1} vs {last_col2}'])
            for col in range(1, 10):
                ws_output.cell(row=row_num+1, column=col).fill = PatternFill(start_color=colors['Structure mismatch'], end_color=colors['Structure mismatch'], fill_type='solid')
            continue

        df1 = pd.DataFrame(ws1.values)
        df2 = pd.DataFrame(ws2.values)

        processed_cells1 = set()
        processed_cells2 = set()
        changed_cells1 = set()
        changed_cells2 = set()

        for col in range(last_col1):
            hash_dict1 = {}
            hash_dict2 = {}

            for row in range(1, len(df1)):
                if (row, col) in processed_cells1:
                    continue
                values1 = [v for i, v in enumerate(df1.iloc[row, :col+1].tolist()) 
                           if pd.notna(v) and v != '' and (row, i) not in changed_cells1]
                if not values1:
                    continue
                hash_key = create_hash(values1)
                hash_dict1[hash_key] = (row, col)

            for row in range(1, len(df2)):
                if (row, col) in processed_cells2:
                    continue
                values2 = [v for i, v in enumerate(df2.iloc[row, :col+1].tolist()) 
                           if pd.notna(v) and v != '' and (row, i) not in changed_cells2]
                if not values2:
                    continue
                hash_key = create_hash(values2)
                hash_dict2[hash_key] = (row, col)

            for hash_key, (row1, _) in hash_dict1.items():
                if hash_key in hash_dict2:
                    row2, _ = hash_dict2[hash_key]
                    if row1 != row2:
                        # Cell moved
                        row_num += 1
                        function_id = df1.iloc[row1, 0]
                        function_name = function_details.get(function_id, {}).get('name', '')
                        owner = function_details.get(function_id, {}).get('owner', '')
                        ws_output.append([row_num, function_name, owner, sheet_name, 
                                          f'{get_column_letter(col+1)}{row1+1}', df1.iloc[row1, col],
                                          f'{get_column_letter(col+1)}{row2+1}', df2.iloc[row2, col],
                                          'Cell value moved'])
                        for c in range(1, 10):
                            ws_output.cell(row=row_num+1, column=c).fill = PatternFill(start_color=colors['Cell value moved'], end_color=colors['Cell value moved'], fill_type='solid')
                    processed_cells1.add((row1, col))
                    processed_cells2.add((row2, col))
                else:
                    # Check for partial matches
                    partial_hash1 = create_hash([v for i, v in enumerate(df1.iloc[row1, :col].tolist()) 
                                                 if (row1, i) not in changed_cells1])
                    matches = [r for h, (r, _) in hash_dict2.items() 
                               if create_hash([v for i, v in enumerate(df2.iloc[r, :col].tolist()) 
                                               if (r, i) not in changed_cells2]) == partial_hash1]
                    if matches:
                        for match in matches:
                            change_type = compare_strings(df1.iloc[row1, col], df2.iloc[match, col])
                            if change_type != 'No change':
                                row_num += 1
                                function_id = df1.iloc[row1, 0]
                                function_name = function_details.get(function_id, {}).get('name', '')
                                owner = function_details.get(function_id, {}).get('owner', '')
                                summary = f"{change_type}"
                                if row1 != match:
                                    summary += " and Cell value moved"
                                ws_output.append([row_num, function_name, owner, sheet_name, 
                                                  f'{get_column_letter(col+1)}{row1+1}', df1.iloc[row1, col],
                                                  f'{get_column_letter(col+1)}{match+1}', df2.iloc[match, col],
                                                  summary])
                                for c in range(1, 10):
                                    ws_output.cell(row=row_num+1, column=c).fill = PatternFill(start_color=colors[change_type], end_color=colors[change_type], fill_type='solid')
                                changed_cells1.add((row1, col))
                                changed_cells2.add((match, col))
                            processed_cells1.add((row1, col))
                            processed_cells2.add((match, col))
                    else:
                        # Cell deleted
                        row_num += 1
                        function_id = df1.iloc[row1, 0]
                        function_name = function_details.get(function_id, {}).get('name', '')
                        owner = function_details.get(function_id, {}).get('owner', '')
                        ws_output.append([row_num, function_name, owner, sheet_name, 
                                          f'{get_column_letter(col+1)}{row1+1}', df1.iloc[row1, col],
                                          '', '', 'Cell value deleted'])
                        for c in range(1, 10):
                            ws_output.cell(row=row_num+1, column=c).fill = PatternFill(start_color=colors['Cell value deleted'], end_color=colors['Cell value deleted'], fill_type='solid')
                        changed_cells1.add((row1, col))
                    processed_cells1.add((row1, col))

            # Check for added cells
            for hash_key, (row2, _) in hash_dict2.items():
                if (row2, col) not in processed_cells2:
                    row_num += 1
                    function_id = df2.iloc[row2, 0]
                    function_name = function_details.get(function_id, {}).get('name', '')
                    owner = function_details.get(function_id, {}).get('owner', '')
                    ws_output.append([row_num, function_name, owner, sheet_name, 
                                      '', '',
                                      f'{get_column_letter(col+1)}{row2+1}', df2.iloc[row2, col],
                                      'Cell value added'])
                    for c in range(1, 10):
                        ws_output.cell(row=row_num+1, column=c).fill = PatternFill(start_color=colors['Cell value added'], end_color=colors['Cell value added'], fill_type='solid')
                    changed_cells2.add((row2, col))
                    processed_cells2.add((row2, col))

    # Add color legends
    ws_output['K2'] = 'Color Legend'
    ws_output['K2'].font = Font(bold=True)
    for i, (change_type, color) in enumerate(colors.items(), start=3):
        cell = ws_output.cell(row=i, column=11, value=change_type)
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

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
file1_path = 'path/to/Report - Apr\'24.xlsx'
file2_path = 'path/to/Report - Jun\'24.xlsx'
output_path = 'path/to/output.xlsx'
compare_excel_files(file1_path, file2_path, output_path)
