import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
import os
import hashlib
from difflib import SequenceMatcher
import argparse
import sys
import logging
from typing import Dict, List, Tuple, Set
from tqdm import tqdm
import pandas as pd
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import json
import csv

# Set up logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def unmerge_cells(worksheet: openpyxl.worksheet.worksheet.Worksheet) -> None:
    """
    Unmerge all merged cells in the worksheet and copy the merged value to each cell.
    """
    try:
        merged_ranges = list(worksheet.merged_cells.ranges)
        for merged_range in merged_ranges:
            worksheet.unmerge_cells(str(merged_range))
            value = worksheet.cell(merged_range.min_row, merged_range.min_col).value
            for row in range(merged_range.min_row, merged_range.max_row + 1):
                for col in range(merged_range.min_col, merged_range.max_col + 1):
                    worksheet.cell(row, col, value)
    except Exception as e:
        logger.error(f"Error in unmerging cells: {e}")
        raise

def generate_hash(values: List[str]) -> str:
    """
    Generate a hash value based on a list of values.

    Parameters:
        values (List[str]): List of values to hash.

    Returns:
        str: A hash string representing the combined values.
    """
    hash_input = '|'.join([str(v) for v in values])
    return hashlib.blake2b(hash_input.encode('utf-8'), digest_size=16).hexdigest()

def compare_strings(s1: str, s2: str) -> float:
    """
    Compare two strings and return a similarity ratio using SequenceMatcher.

    Parameters:
        s1 (str): The first string to compare.
        s2 (str): The second string to compare.

    Returns:
        float: A similarity ratio between 0 and 1.
    """
    s1 = str(s1).strip().lower()
    s2 = str(s2).strip().lower()
    return SequenceMatcher(None, s1, s2).ratio()

def categorize_change(ratio: float, minor_threshold: float, major_threshold: float) -> str:
    """
    Categorize the type of change based on the similarity ratio.

    Parameters:
        ratio (float): The similarity ratio between 0 and 1.
        minor_threshold (float): Threshold above which a change is considered minor.
        major_threshold (float): Threshold above which a change is considered major.

    Returns:
        str: The category of change ('No change', 'Minor change', 'Major change', 'Substantial change').
    """
    if ratio == 1:
        return 'No change'
    elif ratio >= minor_threshold:
        return 'Minor change'
    elif ratio >= major_threshold:
        return 'Major change'
    else:
        return 'Substantial change'

def recursive_match(
    cell_data1: List[Dict],
    cell_data2: List[Dict],
    matched_cells1: Set[int],
    matched_cells2: Set[int],
    level: int,
    minor_threshold: float,
    major_threshold: float
) -> List[Tuple]:
    """
    Recursively match cells by dropping changed ancestors.

    Parameters:
        cell_data1: List of cell dictionaries from source 1.
        cell_data2: List of cell dictionaries from source 2.
        matched_cells1: Set of indices of matched cells from source 1.
        matched_cells2: Set of indices of matched cells from source 2.
        level: Current recursion level.
        minor_threshold: Threshold for minor changes.
        major_threshold: Threshold for major changes.

    Returns:
        List[Tuple]: List of matched cells and their change types.
    """
    if level == 0 or not cell_data1 or not cell_data2:
        return []

    results = []
    # Build hash maps for current level
    hash_map1 = {}
    hash_map2 = {}
    for idx, cell in enumerate(cell_data1):
        if idx in matched_cells1:
            continue
        ancestors = cell['ancestors'][:level]
        full_values = ancestors + [cell['value']]
        cell_hash = generate_hash(full_values)
        hash_map1.setdefault(cell_hash, []).append((idx, cell))

    for idx, cell in enumerate(cell_data2):
        if idx in matched_cells2:
            continue
        ancestors = cell['ancestors'][:level]
        full_values = ancestors + [cell['value']]
        cell_hash = generate_hash(full_values)
        hash_map2.setdefault(cell_hash, []).append((idx, cell))

    # Perform inner join on hashes
    common_hashes = set(hash_map1.keys()).intersection(set(hash_map2.keys()))

    # Match cells with common hashes
    for cell_hash in common_hashes:
        cells1 = hash_map1[cell_hash]
        cells2 = hash_map2[cell_hash]
        for idx1, cell1 in cells1:
            if idx1 in matched_cells1:
                continue
            for idx2, cell2 in cells2:
                if idx2 in matched_cells2:
                    continue
                # Compare values
                val1 = str(cell1['value']).strip()
                val2 = str(cell2['value']).strip()
                ratio = compare_strings(val1, val2)
                change_type = categorize_change(ratio, minor_threshold, major_threshold)
                if change_type == 'No change':
                    if cell1['address'] != cell2['address']:
                        change_type = 'Moved with no change'
                results.append((cell1, cell2, change_type))
                matched_cells1.add(idx1)
                matched_cells2.add(idx2)
                break

    # Recursively match unmatched cells at lower levels
    results.extend(recursive_match(
        cell_data1, cell_data2, matched_cells1, matched_cells2,
        level - 1, minor_threshold, major_threshold
    ))

    return results

def compare_chunks(chunk1: pd.DataFrame, chunk2: pd.DataFrame, sheet_name: str, minor_threshold: float, major_threshold: float) -> List[Tuple]:
    """
    Compare two chunks of data and return the comparison results.

    Parameters:
        chunk1: DataFrame chunk from the first sheet.
        chunk2: DataFrame chunk from the second sheet.
        sheet_name: Name of the sheet being compared.
        minor_threshold: Threshold for minor changes.
        major_threshold: Threshold for major changes.

    Returns:
        List[Tuple]: List of comparison results.
    """
    results = []
    
    # Convert DataFrames to list of dictionaries for easier processing
    data1 = chunk1.to_dict('records')
    data2 = chunk2.to_dict('records')
    
    cell_data1 = []
    cell_data2 = []

    # Prepare cell data for comparison
    for idx, row in enumerate(data1):
        ancestors = list(row.values())[:-1]
        cell_data1.append({
            'sheet': sheet_name,
            'value': list(row.values())[-1],
            'address': f"{chunk1.index[idx]}{chunk1.columns[-1]}",
            'header': chunk1.columns[-1],
            'ancestors': ancestors
        })

    for idx, row in enumerate(data2):
        ancestors = list(row.values())[:-1]
        cell_data2.append({
            'sheet': sheet_name,
            'value': list(row.values())[-1],
            'address': f"{chunk2.index[idx]}{chunk2.columns[-1]}",
            'header': chunk2.columns[-1],
            'ancestors': ancestors
        })

    # Perform recursive matching
    max_level = max(len(cell['ancestors']) for cell in cell_data1 + cell_data2) + 1
    matched_cells1 = set()
    matched_cells2 = set()
    
    matched_results = recursive_match(
        cell_data1, cell_data2, matched_cells1, matched_cells2,
        max_level, minor_threshold, major_threshold
    )
    
    results.extend(matched_results)

    # Process unmatched cells
    for idx, cell in enumerate(cell_data1):
        if idx not in matched_cells1:
            results.append((cell, None, 'Cell deleted'))

    for idx, cell in enumerate(cell_data2):
        if idx not in matched_cells2:
            results.append((None, cell, 'Cell added'))

    return results

def compare_sheets(sheet1: pd.DataFrame, sheet2: pd.DataFrame, sheet_name: str, minor_threshold: float, major_threshold: float, chunk_size: int) -> List[Tuple]:
    """
    Compare two sheets and return the comparison results.

    Parameters:
        sheet1: DataFrame of the first sheet.
        sheet2: DataFrame of the second sheet.
        sheet_name: Name of the sheet being compared.
        minor_threshold: Threshold for minor changes.
        major_threshold: Threshold for major changes.
        chunk_size: Number of rows to process at a time.

    Returns:
        List[Tuple]: List of comparison results.
    """
    results = []
    
    # Process the sheets in chunks
    for start in range(0, len(sheet1), chunk_size):
        end = start + chunk_size
        chunk1 = sheet1.iloc[start:end]
        chunk2 = sheet2.iloc[start:end]
        
        chunk_results = compare_chunks(chunk1, chunk2, sheet_name, minor_threshold, major_threshold)
        results.extend(chunk_results)
    
    return results

def process_sheet(args):
    """
    Process a single sheet for comparison.

    Parameters:
        args: Tuple containing (sheet_name, file1_path, file2_path, minor_threshold, major_threshold, chunk_size)

    Returns:
        Tuple: (sheet_name, comparison_results)
    """
    sheet_name, file1_path, file2_path, minor_threshold, major_threshold, chunk_size = args
    try:
        sheet1 = pd.read_excel(file1_path, sheet_name=sheet_name)
        sheet2 = pd.read_excel(file2_path, sheet_name=sheet_name)
        results = compare_sheets(sheet1, sheet2, sheet_name, minor_threshold, major_threshold, chunk_size)
        return sheet_name, results
    except Exception as e:
        logger.error(f"Error processing sheet {sheet_name}: {e}")
        return sheet_name, []

def compare_excel_files(
    file1_path: str,
    file2_path: str,
    output_path: str,
    minor_threshold: float,
    major_threshold: float,
    ignore_sheets: List[str],
    chunk_size: int,
    num_processes: int,
    output_format: str
) -> None:
    """
    Main function to compare two Excel files and generate a comparison report.
    """
    try:
        # Get list of sheet names
        wb1 = openpyxl.load_workbook(file1_path, read_only=True)
        wb2 = openpyxl.load_workbook(file2_path, read_only=True)
        
        sheets_to_compare = [sheet for sheet in wb1.sheetnames if sheet in wb2.sheetnames and sheet not in ignore_sheets]
        
        # Close workbooks to free up memory
        wb1.close()
        wb2.close()
        
    except Exception as e:
        logger.error(f"Error loading workbooks: {e}")
        sys.exit(1)

    # Prepare arguments for multiprocessing
    args_list = [(sheet, file1_path, file2_path, minor_threshold, major_threshold, chunk_size) for sheet in sheets_to_compare]

    # Process sheets in parallel
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        results = list(tqdm(executor.map(process_sheet, args_list), total=len(args_list), desc="Processing sheets"))

    # Aggregate results
    all_results = []
    for sheet_name, sheet_results in results:
        all_results.extend([(sheet_name,) + result for result in sheet_results])

    # Generate output based on the specified format
    if output_format == 'excel':
        generate_excel_output(all_results, output_path, file1_path, file2_path)
    elif output_format == 'csv':
        generate_csv_output(all_results, output_path)
    elif output_format == 'json':
        generate_json_output(all_results, output_path)
    else:
        logger.error(f"Unsupported output format: {output_format}")
        sys.exit(1)

    logger.info(f"Comparison report saved to {output_path}")

def generate_excel_output(results: List[Tuple], output_path: str, file1_path: str, file2_path: str) -> None:
    """
    Generate an Excel output file with the comparison results.
    """
    wb_output = openpyxl.Workbook()
    ws_output = wb_output.active
    ws_output.title = 'Comparison'

    # Define colors for different types of changes
    colors = {
        'Cell added': 'C6EFCE',
        'Cell deleted': 'FFC7CE',
        'Minor change': 'FFEB9C',
        'Major change': 'FFD966',
        'Substantial change': 'F4B084',
        'Moved with no change': 'D9E1F2',
        'No change': 'FFFFFF'
    }

    # Set up the header row
    headers = ['Sr. No', 'Sheet Name', 'Source 1 Cell', 'Source 1 Value', 'Source 2 Cell', 'Source 2 Value', 'Change Summary']
    ws_output.append(headers)

    # Format the header row
    for col in range(1, len(headers) + 1):
        cell = ws_output.cell(row=1, column=col)
        cell.font = Font(bold=True, color='000000')
        cell.fill = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Add source file details
    ws_output['I2'] = 'Source 1:'
    ws_output['J2'] = os.path.basename(file1_path)
    ws_output['I3'] = 'Source 2:'
    ws_output['J3'] = os.path.basename(file2_path)

    # Add comparison results
    for idx, result in enumerate(results, start=2):
        sheet_name, cell1, cell2, change_type = result
        ws_output.append([
            idx - 1,  # Sr. No
            sheet_name,
            cell1['address'] if cell1 else '',
            cell1['value'] if cell1 else '',
            cell2['address'] if cell2 else '',
            cell2['value'] if cell2['value'] if cell2 else '',
            change_type
        ])
        
        # Apply color formatting
        for col in range(1, 8):
            ws_output.cell(row=idx, column=col).fill = PatternFill(
                start_color=colors.get(change_type, 'FFFFFF'),
                end_color=colors.get(change_type, 'FFFFFF'),
                fill_type='solid'
            )

    # Add color legends
    ws_output['I5'] = 'Color Legend'
    ws_output['I5'].font = Font(bold=True)
    for i, (change_type, color) in enumerate(colors.items(), start=6):
        cell = ws_output.cell(row=i, column=9, value=change_type)
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    # Adjust column widths
    for col in ws_output.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min((max_length + 2), 50)  # Cap width at 50
        ws_output.column_dimensions[column].width = adjusted_width

    # Save the output workbook
    wb_output.save(output_path)

def generate_csv_output(results: List[Tuple], output_path: str) -> None:
    """
    Generate a CSV output file with the comparison results.
    """
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Sr. No', 'Sheet Name', 'Source 1 Cell', 'Source 1 Value', 'Source 2 Cell', 'Source 2 Value', 'Change Summary'])
        
        for idx, (sheet_name, cell1, cell2, change_type) in enumerate(results, start=1):
            writer.writerow([
                idx,
                sheet_name,
                cell1['address'] if cell1 else '',
                cell1['value'] if cell1 else '',
                cell2['address'] if cell2 else '',
                cell2['value'] if cell2 else '',
                change_type
            ])

def generate_json_output(results: List[Tuple], output_path: str) -> None:
    """
    Generate a JSON output file with the comparison results.
    """
    json_results = []
    for idx, (sheet_name, cell1, cell2, change_type) in enumerate(results, start=1):
        json_results.append({
            'Sr. No': idx,
            'Sheet Name': sheet_name,
            'Source 1 Cell': cell1['address'] if cell1 else '',
            'Source 1 Value': cell1['value'] if cell1 else '',
            'Source 2 Cell': cell2['address'] if cell2 else '',
            'Source 2 Value': cell2['value'] if cell2 else '',
            'Change Summary': change_type
        })
    
    with open(output_path, 'w', encoding='utf-8') as jsonfile:
        json.dump(json_results, jsonfile, indent=2)

def main():
    """
    Main function to handle command-line arguments and initiate the comparison process.
    """
    parser = argparse.ArgumentParser(description='Compare two Excel files and generate a comparison report.')
    parser.add_argument('-f1', '--file1', type=str, required=True, help='Path to the first Excel file.')
    parser.add_argument('-f2', '--file2', type=str, required=True, help='Path to the second Excel file.')
    parser.add_argument('-o', '--output', type=str, required=True, help='Path to the output file.')
    parser.add_argument('-mth', '--minor_threshold', type=float, default=0.8, help='Threshold for minor changes (default: 0.8).')
    parser.add_argument('-majth', '--major_threshold', type=float, default=0.5, help='Threshold for major changes (default: 0.5).')
    parser.add_argument('-is', '--ignore_sheets', nargs='*', default=[], help='Sheets to ignore during comparison.')
    parser.add_argument('-cs', '--chunk_size', type=int, default=1000, help='Number of rows to process at a time (default: 1000).')
    parser.add_argument('-p', '--processes', type=int, default=multiprocessing.cpu_count(), help='Number of processes to use (default: number of CPU cores).')
    parser.add_argument('-f', '--format', choices=['excel', 'csv', 'json'], default='excel', help='Output format (default: excel).')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging.')

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Validate thresholds
    if not 0 <= args.minor_threshold <= 1 or not 0 <= args.major_threshold <= 1:
        logger.error("Thresholds must be between 0 and 1.")
        sys.exit(1)
    if args.minor_threshold <= args.major_threshold:
        logger.error("Minor threshold must be greater than major threshold.")
        sys.exit(1)

    # Validate file paths
    if not os.path.exists(args.file1):
        logger.error(f"File not found: {args.file1}")
        sys.exit(1)
    if not os.path.exists(args.file2):
        logger.error(f"File not found: {args.file2}")
        sys.exit(1)

    # Log configurations
    logger.info(f"Comparing {args.file1} and {args.file2}")
    logger.info(f"Output will be saved to {args.output}")
    logger.info(f"Minor change threshold: {args.minor_threshold}")
    logger.info(f"Major change threshold: {args.major_threshold}")
    logger.info(f"Chunk size: {args.chunk_size}")
    logger.info(f"Number of processes: {args.processes}")
    logger.info(f"Output format: {args.format}")
    if args.ignore_sheets:
        logger.info(f"Ignoring sheets: {', '.join(args.ignore_sheets)}")

    # Run the comparison
    try:
        compare_excel_files(
            file1_path=args.file1,
            file2_path=args.file2,
            output_path=args.output,
            minor_threshold=args.minor_threshold,
            major_threshold=args.major_threshold,
            ignore_sheets=args.ignore_sheets,
            chunk_size=args.chunk_size,
            num_processes=args.processes,
            output_format=args.format
        )
        logger.info("Comparison completed successfully.")
    except Exception as e:
        logger.error(f"An error occurred during comparison: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
