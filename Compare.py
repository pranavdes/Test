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
    return hashlib.md5(''.join(str(v) for v in values).encode()).hexdigest()

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

    row_num = 1

    for sheet_name in wb1.sheetnames:
        ws1 = wb1[sheet_name]
        unmerge_cells(ws1)
        
        if sheet_name in wb2.sheetnames:
            ws2 = wb2[sheet_name]
            unmerge_cells(ws2)

            df1 = pd.DataFrame(ws1.values)
            df2 = pd.DataFrame(ws2.values)

            # Create hash dictionaries for both sheets
            hash_dict1 = {}
            hash_dict2 = {}

            for i, row in df1.iterrows():
                for j in range(len(row)):
                    hash_key = create_hash(row[:j+1])
                    if hash_key not in hash_dict1:
                        hash_dict1[hash_key] = []
                    hash_dict1[hash_key].append((i, j))

            for i, row in df2.iterrows():
                for j in range(len(row)):
                    hash_key = create_hash(row[:j+1])
                    if hash_key not in hash_dict2:
                        hash_dict2[hash_key] = []
                    hash_dict2[hash_key].append((i, j))

            # Compare cells
            processed_cells1 = set()
            processed_cells2 = set()

            for hash_key, positions1 in hash_dict1.items():
                for i1, j1 in positions1:
                    if (i1, j1) in processed_cells1:
                        continue

                    if hash_key in hash_dict2:
                        for i2, j2 in hash_dict2[hash_key]:
                            if i1 != i2 or j1 != j2:
                                # Cell moved
                                row_num += 1
                                function_id = df1.iloc[i1, 0]
                                function_name = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('name', '')
                                owner = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('owner', '')
                                ws_output.append([row_num, function_name, owner, sheet_name, 
                                                  f'{get_column_letter(j1+1)}{i1+1}', df1.iloc[i1, j1],
                                                  f'{get_column_letter(j2+1)}{i2+1}', df2.iloc[i2, j2],
                                                  'Cell value moved'])
                                for col in range(1, 10):
                                    ws_output.cell(row=row_num, column=col).fill = PatternFill(start_color=colors['Cell value moved'], end_color=colors['Cell value moved'], fill_type='solid')
                            processed_cells1.add((i1, j1))
                            processed_cells2.add((i2, j2))
                            break
                    else:
                        # Check for similar content
                        partial_hash = create_hash(df1.iloc[i1, :j1])
                        matches = [(i, j) for h, positions in hash_dict2.items() for i, j in positions if create_hash(df2.iloc[i, :j]) == partial_hash]
                        if matches:
                            best_match = max(matches, key=lambda x: SequenceMatcher(None, str(df1.iloc[i1, j1]), str(df2.iloc[x[0], x[1]])).ratio())
                            i2, j2 = best_match
                            change_type = compare_strings(df1.iloc[i1, j1], df2.iloc[i2, j2])
                            if change_type != 'No change':
                                row_num += 1
                                function_id = df1.iloc[i1, 0]
                                function_name = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('name', '')
                                owner = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('owner', '')
                                ws_output.append([row_num, function_name, owner, sheet_name, 
                                                  f'{get_column_letter(j1+1)}{i1+1}', df1.iloc[i1, j1],
                                                  f'{get_column_letter(j2+1)}{i2+1}', df2.iloc[i2, j2],
                                                  change_type])
                                for col in range(1, 10):
                                    ws_output.cell(row=row_num, column=col).fill = PatternFill(start_color=colors[change_type], end_color=colors[change_type], fill_type='solid')
                            processed_cells1.add((i1, j1))
                            processed_cells2.add((i2, j2))
                        else:
                            # Cell deleted
                            row_num += 1
                            function_id = df1.iloc[i1, 0]
                            function_name = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('name', '')
                            owner = get_function_details(wb1['Core OCIR Data']).get(function_id, {}).get('owner', '')
                            ws_output.append([row_num, function_name, owner, sheet_name, 
                                              f'{get_column_letter(j1+1)}{i1+1}', df1.iloc[i1, j1],
                                              '', '', 'Cell value deleted'])
                            for col in range(1, 10):
                                ws_output.cell(row=row_num, column=col).fill = PatternFill(start_color=colors['Cell value deleted'], end_color=colors['Cell value deleted'], fill_type='solid')
                        processed_cells1.add((i1, j1))

            # Check for added cells
            for hash_key, positions2 in hash_dict2.items():
                for i2, j2 in positions2:
                    if (i2, j2) not in processed_cells2:
                        row_num += 1
                        function_id = df2.iloc[i2, 0]
                        function_name = get_function_details(wb2['Core OCIR Data']).get(function_id, {}).get('name', '')
                        owner = get_function_details(wb2['Core OCIR Data']).get(function_id, {}).get('owner', '')
                        ws_output.append([row_num, function_name, owner, sheet_name, 
                                          '', '',
                                          f'{get_column_letter(j2+1)}{i2+1}', df2.iloc[i2, j2],
                                          'Cell value added'])
                        for col in range(1, 10):
                            ws_output.cell(row=row_num, column=col).fill = PatternFill(start_color=colors['Cell value added'], end_color=colors['Cell value added'], fill_type='solid')

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