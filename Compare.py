import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
from difflib import SequenceMatcher
import os

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

def compare_content(old_content, new_content):
    if old_content == new_content:
        return None
    ratio = SequenceMatcher(None, str(old_content), str(new_content)).ratio()
    if ratio > 0.9:
        return 'Cell value changed slightly'
    elif ratio > 0.5:
        return 'Cell value changed partially'
    else:
        return 'Cell value changed completely'

def compare_excel_files(file1_path, file2_path, output_path):
    wb1 = openpyxl.load_workbook(file1_path, data_only=True)
    wb2 = openpyxl.load_workbook(file2_path, data_only=True)
    wb_output = openpyxl.Workbook()
    ws_output = wb_output.active
    ws_output.title = 'Comparison'

    colors = {
        'Cell value added': 'CCFFCC',
        'Cell value deleted': 'FFCCCC',
        'Cell value changed slightly': 'FFFFCC',
        'Cell value changed partially': 'FFD700',
        'Cell value changed completely': 'FF6347',
        'Cell value moved': 'E6E6FA'
    }

    # Get function details
    function_details = get_function_details(wb1['Core OCIR Data'])

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
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center')

    row_num = 1
    for sheet_name in wb1.sheetnames:
        if sheet_name == 'Core OCIR Data':
            continue

        ws1 = wb1[sheet_name]
        unmerge_cells(ws1)
        
        if sheet_name in wb2.sheetnames:
            ws2 = wb2[sheet_name]
            unmerge_cells(ws2)

            df1 = pd.DataFrame(ws1.values)
            df2 = pd.DataFrame(ws2.values)

            # Track processed cells to avoid duplicates
            processed_cells = set()

            for (r1, c1), v1 in df1.stack().items():
                if (r1, c1) in processed_cells:
                    continue
                
                cell1 = f'{get_column_letter(c1+1)}{r1+1}'
                function_id = df1.iloc[r1, 0] if c1 > 0 else v1
                function_name = function_details.get(function_id, {}).get('name', '')
                owner = function_details.get(function_id, {}).get('owner', '')

                found = False
                for (r2, c2), v2 in df2.stack().items():
                    if (r2, c2) in processed_cells:
                        continue
                    
                    if str(v1).strip() == str(v2).strip():
                        if r1 != r2 or c1 != c2:
                            cell2 = f'{get_column_letter(c2+1)}{r2+1}'
                            row_num += 1
                            ws_output.append([row_num, function_name, owner, sheet_name, cell1, v1, cell2, v2, 'Cell value moved'])
                            for col in range(1, 10):
                                ws_output.cell(row=row_num, column=col).fill = PatternFill(start_color=colors['Cell value moved'], end_color=colors['Cell value moved'], fill_type='solid')
                        found = True
                        processed_cells.add((r1, c1))
                        processed_cells.add((r2, c2))
                        break
                    elif compare_content(v1, v2):
                        cell2 = f'{get_column_letter(c2+1)}{r2+1}'
                        change_type = compare_content(v1, v2)
                        row_num += 1
                        ws_output.append([row_num, function_name, owner, sheet_name, cell1, v1, cell2, v2, change_type])
                        for col in range(1, 10):
                            ws_output.cell(row=row_num, column=col).fill = PatternFill(start_color=colors[change_type], end_color=colors[change_type], fill_type='solid')
                        found = True
                        processed_cells.add((r1, c1))
                        processed_cells.add((r2, c2))
                        break

                if not found:
                    row_num += 1
                    ws_output.append([row_num, function_name, owner, sheet_name, cell1, v1, '', '', 'Cell value deleted'])
                    for col in range(1, 10):
                        ws_output.cell(row=row_num, column=col).fill = PatternFill(start_color=colors['Cell value deleted'], end_color=colors['Cell value deleted'], fill_type='solid')
                    processed_cells.add((r1, c1))

            for (r2, c2), v2 in df2.stack().items():
                if (r2, c2) in processed_cells:
                    continue
                
                cell2 = f'{get_column_letter(c2+1)}{r2+1}'
                function_id = df2.iloc[r2, 0] if c2 > 0 else v2
                function_name = function_details.get(function_id, {}).get('name', '')
                owner = function_details.get(function_id, {}).get('owner', '')
                row_num += 1
                ws_output.append([row_num, function_name, owner, sheet_name, '', '', cell2, v2, 'Cell value added'])
                for col in range(1, 10):
                    ws_output.cell(row=row_num, column=col).fill = PatternFill(start_color=colors['Cell value added'], end_color=colors['Cell value added'], fill_type='solid')

        else:
            for r, row in enumerate(ws1.iter_rows(), start=1):
                for c, cell in enumerate(row, start=1):
                    function_id = ws1.cell(row=r, column=1).value
                    function_name = function_details.get(function_id, {}).get('name', '')
                    owner = function_details.get(function_id, {}).get('owner', '')
                    row_num += 1
                    ws_output.append([row_num, function_name, owner, sheet_name, f'{get_column_letter(c)}{r}', cell.value, '', '', 'Cell value deleted'])
                    for col in range(1, 10):
                        ws_output.cell(row=row_num, column=col).fill = PatternFill(start_color=colors['Cell value deleted'], end_color=colors['Cell value deleted'], fill_type='solid')

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