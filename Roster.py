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
    
    Assumptions:
    - The first row of the table is a header row.
    - 'table_name' matches the Table Name defined under Table Design in Excel.
    """
    # Tables are stored in ws._tables in openpyxl
    for tbl in ws._tables:
        if tbl.name == table_name:
            ref = tbl.ref  # e.g. "A1:C10"
            cells = ws[ref]
            data = [[cell.value for cell in row] for row in cells]
            # First row is assumed to be the header
            df = pd.DataFrame(data[1:], columns=data[0])
            return df
    raise ValueError(f"Table '{table_name}' not found on worksheet '{ws.title}'.")

def get_working_dates(year, month, public_holidays):
    """
    Returns a list of working dates (datetime objects) for the given month and year,
    excluding weekends and public holidays.
    """
    num_days = calendar.monthrange(year, month)[1]
    all_dates = [datetime(year, month, day) for day in range(1, num_days + 1)]
    
    # Convert public holiday dates to date objects for easier comparison
    holiday_dates = set(pd.to_datetime(d).date() for d in public_holidays)
    
    # Monday=0, Sunday=6 => so <5 means Mon-Fri
    working = [d for d in all_dates if d.weekday() < 5 and d.date() not in holiday_dates]
    return working

def matches_day_descriptor(date, descriptor, working_dates):
    """
    Checks if a given date matches a descriptor like '1st Tue' or 'Last Fri'.
    For example, for '1st Tue' it returns True if the date is the first Tuesday in working_dates.
    """
    try:
        parts = descriptor.split()
        if len(parts) != 2:
            return False
        
        occurrence, weekday_code = parts  # e.g. "1st", "Tue"
        day_abbr = date.strftime('%a')    # e.g. "Tue"
        
        # Compare ignoring case
        if not day_abbr.lower().startswith(weekday_code.lower()):
            return False
        
        # Collect all working dates in the same month with the same weekday
        same_weekday = [d for d in working_dates if d.month == date.month and d.weekday() == date.weekday()]
        
        if occurrence.lower() == "last":
            return date == same_weekday[-1]
        else:
            # Occurrence might be '1st', '2nd', etc. Let's parse out the digit
            # 1st => 1, 2nd => 2, 3rd => 3, 4th => 4, etc.
            # We'll just take the first character if it's a digit
            num_str = ''.join([c for c in occurrence if c.isdigit()])
            if not num_str.isdigit():
                return False
            idx = int(num_str) - 1  # 0-based index
            if 0 <= idx < len(same_weekday):
                return date == same_weekday[idx]
            else:
                return False
    except Exception:
        return False

def generate_roster_schedule(excel_file):
    """
    Generates a team rostering schedule for a given month-year based on:
      - Two named cells: 'OfficePercentage' and 'TargetMonthYear'
      - Six Excel tables: 'EmployeeData', 'SeatData', 'PublicHolidays',
                          'SubTeamOfficeDays', 'SpecialSubTeamDays', 'SeatPreferences'
    The resulting schedule is written to a new sheet named after 'TargetMonthYear'.
    """
    try:
        # Load the workbook
        wb = load_workbook(excel_file)
        
        # Retrieve the 'Static Data' sheet (assuming that is where all tables live)
        static_ws = wb["Static Data"]
        
        # 1. Read Named Cells
        office_percentage = get_named_cell_value(wb, "OfficePercentage")
        target_month_year = get_named_cell_value(wb, "TargetMonthYear")
        
        # 2. Parse month-year (e.g., "Mar-25")
        if not target_month_year:
            raise ValueError("TargetMonthYear is empty or not defined.")
        
        # Example: "Mar-25" => month=3, year=2025
        month_str, year_str = target_month_year.split("-")
        month = datetime.strptime(month_str, "%b").month
        # Simple logic to handle '25' => 2025, '30' => 2030, etc.
        # If the year part is already full (e.g. "2025"), adjust as needed.
        if len(year_str) == 2:
            year = int("20" + year_str)
        else:
            year = int(year_str)
        
        # 3. Read Data from Excel Tables
        df_employees       = get_table_as_df(static_ws, "EmployeeData")
        df_seats           = get_table_as_df(static_ws, "SeatData")
        df_public_holidays = get_table_as_df(static_ws, "PublicHolidays")
        df_subteam_days    = get_table_as_df(static_ws, "SubTeamOfficeDays")
        df_special_days    = get_table_as_df(static_ws, "SpecialSubTeamDays")
        df_seat_pref       = get_table_as_df(static_ws, "SeatPreferences")
        
        # 4. Compute working days for the month (excluding weekends & public holidays)
        public_holiday_dates = df_public_holidays["Date"]  # Column containing holiday dates
        working_dates = get_working_dates(year, month, public_holiday_dates)
        total_working_days = len(working_dates)
        
        # 5. Determine how many days each employee must be in office
        #    required_days = round( total_working_days * (office_percentage / 100) )
        required_days = round(total_working_days * (office_percentage / 100.0))
        
        # 6. Create dictionaries for easy lookups
        #    - How many days each employee still needs
        #    - Mapping for employee name and sub-team
        employee_remaining = {}
        for _, row in df_employees.iterrows():
            emp_id = row["EmployeeID"]
            employee_remaining[emp_id] = required_days
        
        employee_names = df_employees.set_index("EmployeeID")["EmployeeName"].to_dict()
        emp_subteam_map = df_employees.set_index("EmployeeID")["SubTeam"].to_dict()
        
        # 7. Prepare schedule structure
        #    Key: date -> Value: dict of seat_code -> employee_id
        schedule = {day: {} for day in working_dates}
        
        # -----------------------------------------------------------------
        # 7.1 Assign Fixed Seats
        # -----------------------------------------------------------------
        for _, seat_row in df_seats.iterrows():
            seat_code = seat_row["SeatCode"]
            seat_type = str(seat_row["SeatType"]).strip().lower()
            days_list = [d.strip() for d in str(seat_row["Days"]).split(",")]
            assigned_emp = seat_row.get("AssignedEmployeeID")
            
            if seat_type == "fixed" and pd.notna(assigned_emp):
                for day in working_dates:
                    day_abbr = day.strftime("%a")  # e.g. "Mon", "Tue"
                    day_full = day.strftime("%A")  # e.g. "Monday", "Tuesday"
                    
                    # If the day is in the seat's day list (in either short or full form)
                    if day_abbr in days_list or day_full in days_list:
                        schedule[day][seat_code] = assigned_emp
                        # Decrement the employee's remaining required days if still > 0
                        if employee_remaining.get(assigned_emp, 0) > 0:
                            employee_remaining[assigned_emp] -= 1
        
        # -----------------------------------------------------------------
        # 7.2 Assign Flexible Seats
        # -----------------------------------------------------------------
        for day in working_dates:
            day_abbr = day.strftime("%a")
            day_full = day.strftime("%A")
            
            # Identify which seats are flexible AND unassigned for this day
            available_seats = []
            for _, seat_row in df_seats.iterrows():
                seat_code = seat_row["SeatCode"]
                seat_type = str(seat_row["SeatType"]).strip().lower()
                days_list = [d.strip() for d in str(seat_row["Days"]).split(",")]
                
                if seat_type == "flexible" and (day_abbr in days_list or day_full in days_list):
                    # Check if not already assigned (from some reason)
                    if seat_code not in schedule[day]:
                        available_seats.append(seat_code)
            
            # Check if day is a "special day" for a sub-team (like "1st Tue" => SubTeam)
            special_subteam = None
            for _, sp_row in df_special_days.iterrows():
                descriptor = str(sp_row["DayDescriptor"]).strip()  # e.g. "1st Tue"
                subteam = sp_row["SubTeam"]
                if matches_day_descriptor(day, descriptor, working_dates):
                    special_subteam = subteam
                    break
            
            # Build the list of employees eligible to come in this day
            # 1) If special_subteam is set => only employees from that sub-team
            # 2) Otherwise, employees whose sub-team is scheduled for day_abbr or day_full
            if special_subteam:
                eligible_emps = df_employees[df_employees["SubTeam"] == special_subteam]["EmployeeID"].tolist()
            else:
                # SubTeamOfficeDays => each row: SubTeam, OfficeDays
                # e.g. SubTeam= "TeamA", OfficeDays="Mon,Wed"
                eligible_emps = []
                for _, row_st in df_subteam_days.iterrows():
                    st = row_st["SubTeam"]
                    office_days = [x.strip() for x in str(row_st["OfficeDays"]).split(",")]
                    
                    if day_abbr in office_days or day_full in office_days:
                        # Add employees from that sub-team
                        st_emps = df_employees[df_employees["SubTeam"] == st]["EmployeeID"].tolist()
                        eligible_emps.extend(st_emps)
                # remove duplicates
                eligible_emps = list(set(eligible_emps))
            
            # Filter to only those employees who still need to come in
            eligible_emps = [emp for emp in eligible_emps if employee_remaining.get(emp, 0) > 0]
            
            # We'll track employees assigned for the day to avoid double-assignments
            assigned_today = set()
            
            for seat_code in available_seats:
                # Check seat preferences
                seat_pref_rows = df_seat_pref[df_seat_pref["SeatCode"] == seat_code]
                
                if not seat_pref_rows.empty:
                    # Among the employees who prefer this seat, pick from those who are eligible
                    pref_emp_ids = seat_pref_rows["EmployeeID"].tolist()
                    # Filter to eligible and not assigned yet
                    pref_candidates = [emp for emp in pref_emp_ids if (emp in eligible_emps and emp not in assigned_today)]
                    
                    if pref_candidates:
                        chosen = random.choice(pref_candidates)
                        schedule[day][seat_code] = chosen
                        employee_remaining[chosen] -= 1
                        assigned_today.add(chosen)
                        continue
                
                # If no preference or no pref candidates, assign randomly from remaining
                if eligible_emps:
                    avail_candidates = [emp for emp in eligible_emps if emp not in assigned_today]
                    if avail_candidates:
                        chosen = random.choice(avail_candidates)
                        schedule[day][seat_code] = chosen
                        employee_remaining[chosen] -= 1
                        assigned_today.add(chosen)
        
        # -----------------------------------------------------------------
        # 8. Create/Overwrite the Output Sheet
        # -----------------------------------------------------------------
        if target_month_year in wb.sheetnames:
            out_ws = wb[target_month_year]
            # Optionally, clear old data if you want a fresh start
            for row in out_ws.iter_rows(min_row=1, max_row=out_ws.max_row,
                                        min_col=1, max_col=out_ws.max_column):
                for cell in row:
                    cell.value = None
        else:
            out_ws = wb.create_sheet(title=target_month_year)
        
        # Prepare the header row: Date, Day, then one column per seat
        seat_codes = df_seats["SeatCode"].tolist()
        headers = ["Date", "Day"] + seat_codes
        out_ws.append(headers)
        
        # Prepare sub-team color mapping
        unique_subteams = df_employees["SubTeam"].unique().tolist()
        color_palette = ["FFD7CC", "D7F7D7", "CCD7FF", "FFF2CC", "E2EFDA", "FCE4D6"]
        subteam_color = {st: color_palette[i % len(color_palette)] for i, st in enumerate(unique_subteams)}
        
        # Sort the working dates chronologically
        sorted_dates = sorted(schedule.keys())
        
        for day in sorted_dates:
            row_data = [day.strftime("%Y-%m-%d"), day.strftime("%a")]
            for seat_code in seat_codes:
                emp_id = schedule[day].get(seat_code, "")
                if emp_id:
                    emp_name = employee_names.get(emp_id, "")
                    row_data.append(f"{emp_id} - {emp_name}")
                else:
                    row_data.append("")
            
            out_ws.append(row_data)
        
        # -----------------------------------------------------------------
        # 9. Format the Output Sheet
        # -----------------------------------------------------------------
        # Make header row bold, center-aligned, and highlight
        header_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
        for cell in out_ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Color-code seat assignments based on sub-team
        for row in out_ws.iter_rows(min_row=2, min_col=3, max_col=out_ws.max_column):
            for cell in row:
                if cell.value:
                    # cell.value = "EMP001 - John Doe" => split on ' - '
                    emp_id = cell.value.split(" - ")[0].strip()
                    if emp_id in emp_subteam_map:
                        st = emp_subteam_map[emp_id]
                        fill_color = subteam_color.get(st, "FFFFFF")
                        cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
                        cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Auto-adjust column widths for clarity
        for col in out_ws.columns:
            max_length = 0
            column_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            out_ws.column_dimensions[column_letter].width = max_length + 2
        
        # -----------------------------------------------------------------
        # 10. Save the Workbook
        # -----------------------------------------------------------------
        wb.save(excel_file)
        print("Roster schedule generated successfully.")
    
    except Exception as e:
        print(f"Error generating schedule: {e}")

if __name__ == "__main__":
    excel_filename = "TeamRoster.xlsx"  # Change this to the actual file path
    generate_roster_schedule(excel_filename)