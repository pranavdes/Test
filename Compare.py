import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import os
import hashlib
from difflib import SequenceMatcher
from collections import defaultdict  # Import defaultdict for change_summary
import argparse
import sys
import logging
from typing import Dict, List, Tuple
from tqdm import tqdm

# Set up logging configuration to display messages with timestamp and level
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def unmerge_cells(worksheet: openpyxl.worksheet.worksheet.Worksheet) -> None:
    """
    Unmerge all merged cells in the worksheet and copy the merged value to each cell.

    Parameters:
        worksheet (openpyxl.worksheet.worksheet.Worksheet): The worksheet to process.
    """
    try:
        # Get a list of all merged cell ranges in the worksheet
        merged_ranges = list(worksheet.merged_cells.ranges)
        for merged_range in merged_ranges:
            # Unmerge the cells in the merged range
            worksheet.unmerge_cells(str(merged_range))
            # Get the value from the top-left cell of the merged range
            value = worksheet.cell(merged_range.min_row, merged_range.min_col).value
            # Assign the value to each cell in the previously merged range
            for row in range(merged_range.min_row, merged_range.max_row + 1):
                for col in range(merged_range.min_col, merged_range.max_col + 1):
                    worksheet.cell(row, col, value)
    except Exception as e:
        logger.error(f"Error in unmerging cells: {e}")
        raise

def get_function_details(
    workbook: openpyxl.workbook.workbook.Workbook,
    sheet_name: str,
    key_column: str,
    function_name_column: str,
    owner_column: str
) -> Dict[str, Dict[str, str]]:
    """
    Extract function details from the specified sheet in the workbook.

    Parameters:
        workbook (openpyxl.workbook.workbook.Workbook): The workbook containing the data.
        sheet_name (str): The name of the sheet to extract details from.
        key_column (str): The column name to use as the key (e.g., 'Function ID').
        function_name_column (str): The column name for the function name.
        owner_column (str): The column name for the owner.

    Returns:
        Dict[str, Dict[str, str]]: A dictionary mapping the key to function details.
    """
    function_details = {}
    try:
        # Check if the specified sheet exists in the workbook
        if sheet_name not in workbook.sheetnames:
            logger.warning(f"Sheet '{sheet_name}' not found in workbook. Function details will be empty.")
            return function_details
        
        # Get the worksheet by name
        sheet = workbook[sheet_name]
        # Extract the header row to identify column indices
        headers = [cell.value for cell in sheet[1]]
        
        # Find the indices of the key, function name, and owner columns
        key_index = headers.index(key_column) if key_column in headers else None
        name_index = headers.index(function_name_column) if function_name_column in headers else None
        owner_index = headers.index(owner_column) if owner_column in headers else None
        
        # If the key column is not found, log an error and return
        if key_index is None:
            logger.error(f"Key column '{key_column}' not found in sheet '{sheet_name}'.")
            return function_details
        
        # Iterate over the rows starting from the second row (excluding headers)
        for row in sheet.iter_rows(min_row=2, values_only=True):
            # Get the key value from the row
            key_value = row[key_index]
            if key_value:
                details = {}
                # Get the function name if the index exists
                details['name'] = row[name_index] if name_index is not None else ''
                # Get the owner if the index exists
                details['owner'] = row[owner_index] if owner_index is not None else ''
                # Add the details to the function_details dictionary
                function_details[key_value] = details
    except Exception as e:
        logger.error(f"Error in getting function details: {e}")
        raise
    return function_details

def compare_strings(s1: str, s2: str) -> float:
    """
    Compare two strings and return a similarity ratio using SequenceMatcher.

    Parameters:
        s1 (str): The first string to compare.
        s2 (str): The second string to compare.

    Returns:
        float: A similarity ratio between 0 and 1.
    """
    # Normalize strings by stripping whitespace and converting to lowercase
    s1 = str(s1).strip().lower()
    s2 = str(s2).strip().lower()
    # Compute the similarity ratio
    return SequenceMatcher(None, s1, s2).ratio()

def compare_values(val1, val2) -> float:
    """
    Compare two values and return a similarity ratio, handling different data types appropriately.

    Parameters:
        val1: The first value to compare.
        val2: The second value to compare.

    Returns:
        float: A similarity ratio between 0 and 1.
    """
    # Ensure val1 and val2 are scalar values, not Series
    if isinstance(val1, pd.Series):
        val1 = val1.iloc[0]
    if isinstance(val2, pd.Series):
        val2 = val2.iloc[0]

    # Debug statements (uncomment for detailed logging)
    # logger.debug(f"Comparing values: val1={val1} (type: {type(val1)}), val2={val2} (type: {type(val2)})")
    
    if pd.isna(val1) and pd.isna(val2):
        # Both values are NaN or None, considered identical
        return 1.0  # No change
    elif pd.isna(val1) or pd.isna(val2):
        # One value is NaN/None and the other is not, considered a complete change
        return 0.0  # Complete change
    elif isinstance(val1, str) and isinstance(val2, str):
        # Both values are strings, compare using string similarity
        return compare_strings(val1, val2)
    elif isinstance(val1, (int, float, complex, bool)) and isinstance(val2, (int, float, complex, bool)):
        # Both values are numeric or boolean, compare for equality
        return 1.0 if val1 == val2 else 0.0
    elif isinstance(val1, pd.Timestamp) and isinstance(val2, pd.Timestamp):
        # Both values are timestamps, compare for equality
        return 1.0 if val1 == val2 else 0.0
    else:
        # For other data types, convert to strings and compare
        return compare_strings(str(val1), str(val2))

def categorize_change(ratio: float, minor_threshold: float, major_threshold: float) -> str:
    """
    Categorize the type of change based on the similarity ratio.

    Parameters:
        ratio (float): The similarity ratio between 0 and 1.
        minor_threshold (float): Threshold above which a change is considered minor.
        major_threshold (float): Threshold above which a change is considered major.

    Returns:
        str: The category of change ('No change', 'Minor change', 'Major change', 'Complete change').
    """
    if ratio == 1:
        return 'No change'
    elif ratio > minor_threshold:
        return 'Minor change'
    elif ratio > major_threshold:
        return 'Major change'
    else:
        return 'Complete change'

def process_chunk(
    chunk: pd.DataFrame,
    minor_threshold: float,
    major_threshold: float,
    ignore_columns: List[str]
) -> List[Tuple]:
    """
    Process a chunk of data and return a list of comparison results.

    Parameters:
        chunk (pd.DataFrame): A chunk of the combined DataFrame to process.
        minor_threshold (float): Threshold for minor changes.
        major_threshold (float): Threshold for major changes.
        ignore_columns (List[str]): List of column names to ignore during comparison.

    Returns:
        List[Tuple]: A list of tuples containing comparison results.
    """
    results = []
    # Iterate over each row in the chunk
    for idx, row in chunk.iterrows():
        function_id = idx  # The key value (e.g., Function ID)
        merge_status = row['_merge']  # Indicates if the row is in both, left_only, or right_only

        if merge_status == 'both':
            # Row exists in both dataframes
            # Get the list of base column names (without suffixes)
            columns = set([col[:-8] for col in chunk.columns if col.endswith('_source1')])
            for col_name in columns:
                if col_name in ignore_columns or col_name == '_merge':
                    continue  # Skip ignored columns and '_merge' column
                col1 = f"{col_name}_source1"  # Column name in source1
                col2 = f"{col_name}_source2"  # Corresponding column name in source2
                val1 = row[col1] if col1 in row else None  # Value from source1
                val2 = row[col2] if col2 in row else None  # Value from source2
                # Ensure val1 and val2 are scalar values
                if isinstance(val1, pd.Series):
                    val1 = val1.iloc[0]
                if isinstance(val2, pd.Series):
                    val2 = val2.iloc[0]
                if pd.isna(val1) and pd.isna(val2):
                    continue  # No change if both values are NaN
                elif pd.isna(val1) and pd.notna(val2):
                    # Value added in source2
                    results.append((function_id, '', '', col_name, val2, 'Cell value added'))
                elif pd.notna(val1) and pd.isna(val2):
                    # Value deleted in source2
                    results.append((function_id, col_name, val1, '', '', 'Cell value deleted'))
                else:
                    # Compare the two values
                    ratio = compare_values(val1, val2)
                    change_type = categorize_change(ratio, minor_threshold, major_threshold)
                    if change_type != 'No change':
                        results.append((function_id, col_name, val1, col_name, val2, change_type))
        elif merge_status == 'left_only':
            # Row only exists in source1 (deleted in source2)
            for col in chunk.columns:
                if col.endswith('_source1'):
                    col_name = col[:-8]
                    if col_name in ignore_columns or col_name == '_merge':
                        continue
                    val1 = row[col]
                    # Ensure val1 is a scalar value
                    if isinstance(val1, pd.Series):
                        val1 = val1.iloc[0]
                    if pd.notna(val1):
                        results.append((function_id, col_name, val1, '', '', 'Cell value deleted'))
        elif merge_status == 'right_only':
            # Row only exists in source2 (added in source2)
            for col in chunk.columns:
                if col.endswith('_source2'):
                    col_name = col[:-8]
                    if col_name in ignore_columns or col_name == '_merge':
                        continue
                    val2 = row[col]
                    # Ensure val2 is a scalar value
                    if isinstance(val2, pd.Series):
                        val2 = val2.iloc[0]
                    if pd.notna(val2):
                        results.append((function_id, '', '', col_name, val2, 'Cell value added'))
    return results

def compare_excel_files(
    file1_path: str,
    file2_path: str,
    output_path: str,
    key_column: str,
    function_name_column: str,
    owner_column: str,
    minor_threshold: float,
    major_threshold: float,
    chunk_size: int,
    ignore_columns: List[str],
    ignore_sheets: List[str],
    disable_progress: bool
) -> None:
    """
    Main function to compare two Excel files and generate a comparison report.

    Parameters:
        file1_path (str): Path to the first Excel file.
        file2_path (str): Path to the second Excel file.
        output_path (str): Path to save the output Excel file.
        key_column (str): Column name used as the key to align rows.
        function_name_column (str): Column name for function name.
        owner_column (str): Column name for owner.
        minor_threshold (float): Threshold for minor changes.
        major_threshold (float): Threshold for major changes.
        chunk_size (int): Number of rows to process at a time.
        ignore_columns (List[str]): Columns to ignore during comparison.
        ignore_sheets (List[str]): Sheets to ignore during comparison.
        disable_progress (bool): Whether to disable the progress bar.
    """
    try:
        # Load the Excel workbooks using openpyxl
        wb1 = openpyxl.load_workbook(file1_path, data_only=True)
        wb2 = openpyxl.load_workbook(file2_path, data_only=True)
    except Exception as e:
        logger.error(f"Error loading workbooks: {e}")
        sys.exit(1)

    # Create a new workbook for the output report
    wb_output = openpyxl.Workbook()
    ws_output = wb_output.active
    ws_output.title = 'Comparison'

    # Define colors for different types of changes
    colors = {
        'Cell value added': 'C6EFCE',     # Light green
        'Cell value deleted': 'FFC7CE',   # Light red
        'Minor change': 'FFEB9C',         # Light yellow
        'Major change': 'FFD966',         # Orange
        'Complete change': 'F4B084',      # Light orange
        'Cell value moved': 'D9E1F2',     # Light blue (not used in current code)
        'No change': 'FFFFFF',            # White
        'Structure mismatch': 'FF0000'    # Red
    }

    # Set up the header row in the output worksheet
    headers = ['Sr. No', 'Function Name', 'Owner', 'Sheet Name',
               'Source 1 Column', 'Source 1 Value',
               'Source 2 Column', 'Source 2 Value',
               'Change Summary']
    ws_output.append(headers)

    # Format the header row with styles
    for col in range(1, len(headers) + 1):
        cell = ws_output.cell(row=1, column=col)
        cell.font = Font(bold=True, color='000000')  # Bold font
        cell.fill = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')  # Light blue background
        cell.alignment = Alignment(horizontal='center', vertical='center')  # Center alignment

    # Add source file details to the output worksheet
    ws_output['L2'] = 'Source 1:'
    ws_output['M2'] = os.path.basename(file1_path)  # File name of the first source
    ws_output['L3'] = 'Source 2:'
    ws_output['M3'] = os.path.basename(file2_path)  # File name of the second source

    row_num = 1  # Initialize row number (header is in row 1)

    # Check if both workbooks have the same sheets
    if set(wb1.sheetnames) != set(wb2.sheetnames):
        row_num += 1
        # Add a note about sheet structure mismatch
        ws_output.append([row_num, '', '', '', '', '', '', '', 'Sheet structure mismatch'])
        # Apply red fill to indicate structure mismatch
        for col in range(1, 10):
            ws_output.cell(row=row_num, column=col).fill = PatternFill(
                start_color=colors['Structure mismatch'],
                end_color=colors['Structure mismatch'],
                fill_type='solid'
            )

    # Get function details from a specific sheet (e.g., 'Core OCIR Data')
    try:
        function_details_sheet = 'Core OCIR Data'  # Modify if the sheet name is different
        # Extract function details from both workbooks
        function_details1 = get_function_details(wb1, function_details_sheet, key_column, function_name_column, owner_column)
        function_details2 = get_function_details(wb2, function_details_sheet, key_column, function_name_column, owner_column)
        # Merge the dictionaries, with values from the second workbook overwriting the first in case of duplicate keys
        function_details = {**function_details1, **function_details2}
    except Exception as e:
        logger.error(f"Error getting function details: {e}")
        function_details = {}

    # Initialize a dictionary to keep track of change counts
    change_summary = defaultdict(int)

    # Iterate through each sheet in the first workbook
    for sheet_name in tqdm(wb1.sheetnames, desc="Processing sheets", disable=disable_progress):
        # Skip sheets that are in the ignore list or not present in both workbooks
        if sheet_name in ignore_sheets or sheet_name not in wb2.sheetnames:
            continue

        # Get the corresponding worksheets from both workbooks
        ws1 = wb1[sheet_name]
        ws2 = wb2[sheet_name]

        # Unmerge cells in both worksheets to ensure consistent data
        unmerge_cells(ws1)
        unmerge_cells(ws2)

        # Read data from the worksheets into DataFrames
        data1 = ws1.values  # Generator for rows in ws1
        cols1 = next(data1)  # First row contains column headers
        df1 = pd.DataFrame(data1, columns=cols1)  # Create DataFrame for ws1

        data2 = ws2.values  # Generator for rows in ws2
        cols2 = next(data2)  # First row contains column headers
        df2 = pd.DataFrame(data2, columns=cols2)  # Create DataFrame for ws2

        # Remove columns to ignore from both DataFrames
        df1 = df1.drop(columns=ignore_columns, errors='ignore')
        df2 = df2.drop(columns=ignore_columns, errors='ignore')

        # Strip whitespace from column names and make them lowercase for consistency
        df1.columns = df1.columns.str.strip().str.lower()
        df2.columns = df2.columns.str.strip().str.lower()

        # Also strip whitespace from key_column and other important columns
        key_column_clean = key_column.strip().lower()
        df1.rename(columns={key_column.strip().lower(): key_column_clean}, inplace=True)
        df2.rename(columns={key_column.strip().lower(): key_column_clean}, inplace=True)

        # Ensure that the key column exists in both DataFrames
        if key_column_clean not in df1.columns or key_column_clean not in df2.columns:
            logger.warning(f"Key column '{key_column}' not found in sheet '{sheet_name}'. Skipping this sheet.")
            continue

        # Set the key column as the index for alignment
        df1.set_index(key_column_clean, inplace=True)
        df2.set_index(key_column_clean, inplace=True)

        # Merge the DataFrames on the index (key column), including an indicator for merge status
        combined_df = df1.merge(df2, how='outer', left_index=True, right_index=True,
                                suffixes=('_source1', '_source2'), indicator=True)

        # Process the combined DataFrame in chunks to handle large datasets efficiently
        for i in range(0, len(combined_df), chunk_size):
            chunk = combined_df.iloc[i:i+chunk_size]  # Get a chunk of rows
            results = process_chunk(chunk, minor_threshold, major_threshold, ignore_columns)  # Process the chunk
            
            # Iterate over the results and write them to the output worksheet
            for result in results:
                function_id, col1, val1, col2, val2, change_type = result
                # Retrieve function name and owner using the function ID
                function_details_key = function_id
                function_name = function_details.get(function_details_key, {}).get('name', '')
                owner = function_details.get(function_details_key, {}).get('owner', '')
                
                row_num += 1  # Increment the row number for each result
                # Append the comparison result to the worksheet
                ws_output.append([row_num, function_name, owner, sheet_name,
                                  col1, val1, col2, val2, change_type])
                # Apply color formatting based on the type of change
                for c in range(1, 10):
                    ws_output.cell(row=row_num, column=c).fill = PatternFill(
                        start_color=colors[change_type],
                        end_color=colors[change_type],
                        fill_type='solid'
                    )
                # Update the change summary count
                change_summary[change_type] += 1

    # Add a color legend to the output worksheet for reference
    ws_output['K2'] = 'Color Legend'
    ws_output['K2'].font = Font(bold=True)
    for i, (change_type, color) in enumerate(colors.items(), start=3):
        cell = ws_output.cell(row=i, column=11, value=change_type)
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

    # Add the change summary to the output worksheet
    ws_output['K15'] = 'Change Summary'
    ws_output['K15'].font = Font(bold=True)
    for i, (change_type, count) in enumerate(change_summary.items(), start=16):
        ws_output.cell(row=i, column=11, value=f"{change_type}: {count}")

    # Adjust the column widths for better readability in the output worksheet
    for col in ws_output.columns:
        max_length = 0
        column = col[0].column_letter  # Get the column letter (e.g., 'A', 'B', ...)
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))  # Update max_length if current cell's content is longer
            except:
                pass
        adjusted_width = min((max_length + 2), 100)  # Set a maximum width to avoid excessively wide columns
        ws_output.column_dimensions[column].width = adjusted_width  # Set the column width

    # Save the output workbook to the specified file
    try:
        wb_output.save(output_path)
        logger.info(f"Comparison report saved to {output_path}")
    except Exception as e:
        logger.error(f"Error saving the output workbook: {e}")
        sys.exit(1)

def main():
    """
    Main function to handle command-line arguments and initiate the comparison process.
    """
    # Set up the argument parser to handle command-line inputs
    parser = argparse.ArgumentParser(description='Compare two Excel files and generate a comparison report.')
    parser.add_argument('-f1', '--file1', type=str, help='Path to the first Excel file.')
    parser.add_argument('-f2', '--file2', type=str, help='Path to the second Excel file.')
    parser.add_argument('-o', '--output', type=str, help='Path to the output Excel file.')
    parser.add_argument('-k', '--key_column', type=str, default='Function ID', help='Name of the key column to align rows.')
    parser.add_argument('-fn', '--function_name_column', type=str, default='Function Name', help='Name of the function name column.')
    parser.add_argument('-own', '--owner_column', type=str, default='Owner', help='Name of the owner column.')
    parser.add_argument('-mth', '--minor_threshold', type=float, default=0.8, help='Threshold for minor changes (default: 0.8).')
    parser.add_argument('-majth', '--major_threshold', type=float, default=0.5, help='Threshold for major changes (default: 0.5).')
    parser.add_argument('-cs', '--chunk_size', type=int, default=10000, help='Number of rows to process at a time (default: 10000).')
    parser.add_argument('-ic', '--ignore_columns', nargs='*', default=[], help='Columns to ignore during comparison.')
    parser.add_argument('-is', '--ignore_sheets', nargs='*', default=[], help='Sheets to ignore during comparison.')
    parser.add_argument('--no-progress', action='store_true', help='Disable progress bars.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging.')

    # Parse the command-line arguments
    args = parser.parse_args()

    # Set logging level to DEBUG if verbose flag is provided
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Validate the similarity thresholds to ensure they are between 0 and 1
    if not 0 <= args.minor_threshold <= 1 or not 0 <= args.major_threshold <= 1:
        logger.error("Thresholds must be between 0 and 1.")
        sys.exit(1)
    # Ensure that the minor threshold is greater than the major threshold
    if args.minor_threshold <= args.major_threshold:
        logger.error("Minor threshold must be greater than major threshold.")
        sys.exit(1)

    # Set default file paths if not provided
    file1_path = args.file1 or 'Report - Apr\'24.xlsx'
    file2_path = args.file2 or 'Report - Jun\'24.xlsx'
    output_path = args.output or 'output.xlsx'

    # Validate that the specified files exist
    if not os.path.exists(file1_path):
        logger.error(f"File not found: {file1_path}")
        sys.exit(1)
    if not os.path.exists(file2_path):
        logger.error(f"File not found: {file2_path}")
        sys.exit(1)

    # Log the configurations being used
    logger.info(f"Comparing {file1_path} and {file2_path}")
    logger.info(f"Output will be saved to {output_path}")
    logger.info(f"Using key column: {args.key_column}")
    logger.info(f"Minor change threshold: {args.minor_threshold}")
    logger.info(f"Major change threshold: {args.major_threshold}")
    logger.info(f"Chunk size: {args.chunk_size}")
    if args.ignore_columns:
        logger.info(f"Ignoring columns: {', '.join(args.ignore_columns)}")
    if args.ignore_sheets:
        logger.info(f"Ignoring sheets: {', '.join(args.ignore_sheets)}")

    try:
        # Call the main comparison function with the provided arguments
        compare_excel_files(
            file1_path=file1_path,
            file2_path=file2_path,
            output_path=output_path,
            key_column=args.key_column,
            function_name_column=args.function_name_column,
            owner_column=args.owner_column,
            minor_threshold=args.minor_threshold,
            major_threshold=args.major_threshold,
            chunk_size=args.chunk_size,
            ignore_columns=args.ignore_columns,
            ignore_sheets=args.ignore_sheets,
            disable_progress=args.no_progress
        )
        logger.info("Comparison completed successfully.")
    except Exception as e:
        logger.error(f"An error occurred during comparison: {e}")
        sys.exit(1)

# Entry point of the script
if __name__ == '__main__':
    main()
