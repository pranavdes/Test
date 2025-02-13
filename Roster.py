import calendar
import random
from datetime import datetime
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

def get_named_cell_value(wb, cell_name):
    """
    Retrieves the value from a single-cell named range in the workbook.
    """
    try:
        defined_range = wb.defined_names[cell_name]
        for title, coord in defined_range.destinations:
            ws = wb[title]
            return ws[coord].value
    except KeyError:
        raise ValueError(f"Named cell '{cell_name}' not found in the workbook.")
    except Exception as e:
        raise ValueError(f"Error reading named cell '{cell_name}': {e}")

def get_table_as_df(ws, table_name):
    """
    Reads an Excel Table (ListObject) by its name on a given worksheet
    and returns the contents as a pandas DataFrame.
    Assumes the first row of the table is a header row.
    """
    for tbl in ws._tables:
        if tbl.name == table_name:
            ref = tbl.ref  # e.g. "A1:C10"
            cells = ws[ref]
            data = [[cell.value for cell in row] for row in cells]
            df = pd.DataFrame(data[1:], columns=data[0])
            return df
    raise ValueError(f"Table '{table_name}' not found on worksheet '{ws.title}'.")

def parse_day_descriptor(descriptor):
    """
    Parses a descriptor like:
      - "1st Working Tuesday"
      - "Last Fri"
      - "2nd Monday"
    and returns (occurrence, weekday_str), where:
      - occurrence is an integer (1,2,3,4) or the string "last"
      - weekday_str is a normalized weekday name in lowercase, e.g. "mon", "tuesday"

    This function is more flexible: it ignores extra words like "Working".
    It looks for:
      - One of {"1st", "2nd", "3rd", "4th", "last"} (case-insensitive)
      - A weekday substring that starts with or matches any of
        ["mon", "tue", "wed", "thu", "fri"] or the full name.
    If it can't parse properly, returns (None, None).
    """
    descriptor = descriptor.strip().lower()
    tokens = descriptor.split()
    
    # Potential patterns:
    #   1) "1st" or "last" or "2nd", etc.
    #   2) "working" or other filler
    #   3) "tuesday" or "wed"
    # We'll store occurrence in "occ" and weekday in "wday"
    occ = None
    wday = None
    
    # Helper sets
    valid_occurrences = {"1st", "2nd", "3rd", "4th", "5th", "last"}
    valid_short_days  = ["mon", "tue", "wed", "thu", "fri"]
    valid_full_days   = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    
    for token in tokens:
        # Check if token is an occurrence
        if token in valid_occurrences:
            occ = token
        else:
            # Check if token matches or starts with short day
            # or matches a full day
            # We'll do a simple approach: if token starts with mon/tue/wed/thu/fri or
            # exactly matches monday/tuesday/wednesday/thursday/friday
            for sd in valid_short_days:
                if token.startswith(sd):
                    wday = sd  # "mon", "tue", etc.
                    break
            for fd in valid_full_days:
                if token == fd:
                    wday = fd  # "monday", "tuesday", etc.
                    break
    
    # If we found nothing, return (None, None)
    if not occ or not wday:
        return (None, None)
    
    return (occ, wday)

def matches_day_descriptor(date_obj, descriptor, working_dates):
    """
    Returns True if 'date_obj' matches the descriptor (like "1st Working Tuesday")
    among the given working_dates.
    """
    occ, wday = parse_day_descriptor(descriptor)
    if not occ or not wday:
        return False  # can't parse the descriptor
    
    # We'll unify the actual date's day-of-week to short or full
    # date_obj.weekday() => Monday=0, Tuesday=1, ...
    # We'll compare in a flexible way
    actual_day_short = date_obj.strftime("%a").lower()  # e.g. "mon"
    actual_day_full  = date_obj.strftime("%A").lower()  # e.g. "monday"
    
    # If the descriptor's wday is "mon" or "monday", check if date_obj is Monday
    # We'll define a small mapping from short to numeric:
    short_map = {"mon":0, "tue":1, "wed":2, "thu":3, "fri":4}
    full_map  = {"monday":0, "tuesday":1, "wednesday":2, "thursday":3, "friday":4}
    
    # Determine the numeric weekday from wday
    if wday in short_map:
        needed_wd = short_map[wday]
    elif wday in full_map:
        needed_wd = full_map[wday]
    else:
        return False  # unexpected
    
    if date_obj.weekday() != needed_wd:
        return False
    
    # If the day matches, figure out if it's the "1st", "2nd", "last", etc.
    # Collect all working dates in the same month & year that match this weekday
    same_wd_dates = [d for d in working_dates
                     if d.year == date_obj.year
                     and d.month == date_obj.month
                     and d.weekday() == needed_wd]
    
    if not same_wd_dates:
        return False
    
    # Sort them ascending
    same_wd_dates.sort()
    
    if occ == "last":
        return date_obj == same_wd_dates[-1]
    else:
        # "1st", "2nd", "3rd", "4th", "5th"
        # We'll parse the numeric portion from "1st", "2nd", etc.
        # ignoring "st", "nd", "rd", "th"
        digit_part = "".join([c for c in occ if c.isdigit()])
        if not digit_part.isdigit():
            return False
        index = int(digit_part) - 1  # zero-based
        if 0 <= index < len(same_wd_dates):
            return date_obj == same_wd_dates[index]
        else:
            return False

def generate_roster_schedule(excel_file):
    """
    Generates a team rostering schedule for a given month-year based on:
      - Named cells: 'OfficePercentage' and 'TargetMonthYear'
      - Excel tables: 'EmployeeData', 'SeatData', 'PublicHolidays',
                      'SubTeamOfficeDays', 'SpecialSubTeamDays', 'SeatPreferences'.
    This version:
      - Parses descriptors like "1st Working Tuesday" or "Last Fri" more flexibly.
      - Prints debug info each day to show available seats, special sub-team, and eligible employees.
    """
    try:
        wb = load_workbook(excel_file)
        static_ws = wb["Static Data"]
        
        # 1. Named Cells
        office_percentage = get_named_cell_value(wb, "OfficePercentage")
        target_month_year = get_named_cell_value(wb, "TargetMonthYear")
        
        if not target_month_year:
            raise ValueError("TargetMonthYear is empty or not defined.")
        
        # Parse "Mar-25" => month=3, year=2025
        month_str, year_str = target_month_year.split("-")
        month = datetime.strptime(month_str, "%b").month
        if len(year_str) == 2:
            year = int("20" + year_str)
        else:
            year = int(year_str)
        
        # 2. Read Tables
        df_employees       = get_table_as_df(static_ws, "EmployeeData")
        df_seats           = get_table_as_df(static_ws, "SeatData")
        df_public_holidays = get_table_as_df(static_ws, "PublicHolidays")
        df_subteam_days    = get_table_as_df(static_ws, "SubTeamOfficeDays")
        df_special_days    = get_table_as_df(static_ws, "SpecialSubTeamDays")
        df_seat_pref       = get_table_as_df(static_ws, "SeatPreferences")
        
        # 3. Determine working dates
        public_holiday_dates = df_public_holidays["Date"]
        # Convert to list if needed
        working_dates = get_working_dates(year, month, public_holiday_dates)
        total_working_days = len(working_dates)
        
        required_days = round(total_working_days * (office_percentage / 100.0))
        
        # 4. Setup employee data
        employee_remaining = {}
        for _, row in df_employees.iterrows():
            emp_id = row["EmployeeID"]
            employee_remaining[emp_id] = required_days
        
        employee_names = df_employees.set_index("EmployeeID")["EmployeeName"].to_dict()
        emp_subteam_map = df_employees.set_index("EmployeeID")["SubTeam"].to_dict()
        
        # 5. Prepare schedule
        schedule = {d: {} for d in working_dates}
        
        # --- A) Assign Fixed Seats ---
        for _, seat_row in df_seats.iterrows():
            seat_code = seat_row["SeatCode"]
            seat_type = str(seat_row["SeatType"]).strip().lower()
            # Normalize seat "Days"
            seat_days = [x.strip().lower() for x in str(seat_row["Days"]).split(",")]
            
            assigned_emp = seat_row.get("AssignedEmployeeID")
            
            if seat_type == "fixed" and pd.notna(assigned_emp):
                for day in working_dates:
                    # Check if day matches seat_days
                    day_abbr = day.strftime("%a").lower()   # "mon"
                    day_full = day.strftime("%A").lower()   # "monday"
                    
                    if day_abbr in seat_days or day_full in seat_days:
                        schedule[day][seat_code] = assigned_emp
                        if employee_remaining.get(assigned_emp, 0) > 0:
                            employee_remaining[assigned_emp] -= 1
        
        # --- B) Assign Flexible Seats ---
        for day in sorted(working_dates):
            day_abbr = day.strftime("%a").lower()
            day_full = day.strftime("%A").lower()
            
            # Collect flexible seats not yet assigned
            available_seats = []
            for _, seat_row in df_seats.iterrows():
                seat_code = seat_row["SeatCode"]
                seat_type = str(seat_row["SeatType"]).strip().lower()
                seat_days = [x.strip().lower() for x in str(seat_row["Days"]).split(",")]
                
                if seat_type == "flexible":
                    if (day_abbr in seat_days or day_full in seat_days):
                        if seat_code not in schedule[day]:
                            available_seats.append(seat_code)
            
            # Determine if there's a special sub-team for this day
            special_subteam = None
            for _, sp_row in df_special_days.iterrows():
                descriptor = str(sp_row["DayDescriptor"]).strip()
                sub_team = sp_row["SubTeam"]  # e.g. "C&O", "Team A", etc.
                if matches_day_descriptor(day, descriptor, working_dates):
                    special_subteam = sub_team
                    break  # use the first match we find
            
            # Gather employees from sub-team days
            if special_subteam:
                # Only employees from that sub-team
                eligible_emps = df_employees[df_employees["SubTeam"] == special_subteam]["EmployeeID"].tolist()
            else:
                # Normal sub-team day logic
                # We look at each row in SubTeamOfficeDays
                # If day_abbr or day_full is in row["OfficeDays"], then that sub-team is included
                subteam_matches = []
                for _, st_row in df_subteam_days.iterrows():
                    st_name = st_row["SubTeam"]  # e.g. "C&O"
                    office_days = [x.strip().lower() for x in str(st_row["OfficeDays"]).split(",")]
                    if day_abbr in office_days or day_full in office_days:
                        # Add employees from that sub-team
                        st_emps = df_employees[df_employees["SubTeam"] == st_name]["EmployeeID"].tolist()
                        subteam_matches.extend(st_emps)
                
                # De-duplicate
                eligible_emps = list(set(subteam_matches))
            
            # Filter out employees who have no remaining requirement
            eligible_emps = [emp for emp in eligible_emps if employee_remaining.get(emp, 0) > 0]
            
            # Debug: see what's happening
            print(f"--- {day.strftime('%Y-%m-%d')} ---")
            print(f"  available_seats = {available_seats}")
            print(f"  special_subteam = {special_subteam}")
            print(f"  eligible_emps   = {eligible_emps}")
            
            assigned_today = set()
            
            for seat_code in available_seats:
                # Check seat preferences
                seat_pref_rows = df_seat_pref[df_seat_pref["SeatCode"] == seat_code]
                if not seat_pref_rows.empty:
                    pref_emp_ids = seat_pref_rows["EmployeeID"].tolist()
                    pref_candidates = [emp for emp in pref_emp_ids if emp in eligible_emps and emp not in assigned_today]
                    if pref_candidates:
                        chosen = random.choice(pref_candidates)
                        schedule[day][seat_code] = chosen
                        employee_remaining[chosen] -= 1
                        assigned_today.add(chosen)
                        continue
                
                # Otherwise assign randomly if we still have eligible candidates
                remaining_candidates = [emp for emp in eligible_emps if emp not in assigned_today]
                if remaining_candidates:
                    chosen = random.choice(remaining_candidates)
                    schedule[day][seat_code] = chosen
                    employee_remaining[chosen] -= 1
                    assigned_today.add(chosen)
        
        # --- C) Create/Overwrite Output Sheet ---
        if target_month_year in wb.sheetnames:
            out_ws = wb[target_month_year]
            # Optional: clear existing data
            for row in out_ws.iter_rows(min_row=1, max_row=out_ws.max_row,
                                        min_col=1, max_col=out_ws.max_column):
                for cell in row:
                    cell.value = None
        else:
            out_ws = wb.create_sheet(title=target_month_year)
        
        seat_codes = df_seats["SeatCode"].tolist()
        headers = ["Date", "Day"] + seat_codes
        out_ws.append(headers)
        
        # Sub-team color mapping
        unique_subteams = df_employees["SubTeam"].unique().tolist()
        color_palette = ["FFD7CC", "D7F7D7", "CCD7FF", "FFF2CC", "E2EFDA", "FCE4D6"]
        subteam_color = {st: color_palette[i % len(color_palette)] for i, st in enumerate(unique_subteams)}
        
        for day in sorted(working_dates):
            row_data = [day.strftime("%Y-%m-%d"), day.strftime("%a")]
            for seat_code in seat_codes:
                emp_id = schedule[day].get(seat_code, "")
                if emp_id:
                    emp_name = employee_names.get(emp_id, "")
                    row_data.append(f"{emp_id} - {emp_name}")
                else:
                    row_data.append("")
            out_ws.append(row_data)
        
        # Format the header
        header_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
        for cell in out_ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Color-code seat assignments by sub-team
        for row in out_ws.iter_rows(min_row=2, min_col=3, max_col=out_ws.max_column):
            for cell in row:
                if cell.value:
                    emp_id = cell.value.split(" - ")[0].strip()
                    if emp_id in emp_subteam_map:
                        st = emp_subteam_map[emp_id]
                        fill_color = subteam_color.get(st, "FFFFFF")
                        cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
                        cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Adjust column widths
        for col in out_ws.columns:
            max_length = 0
            column_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            out_ws.column_dimensions[column_letter].width = max_length + 2
        
        wb.save(excel_file)
        print("Roster schedule generated successfully.")
    
    except Exception as e:
        print(f"Error generating schedule: {e}")

if __name__ == "__main__":
    excel_filename = "TeamRoster.xlsx"  # Adjust path as needed
    generate_roster_schedule(excel_filename)