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

def get_working_dates(year, month, public_holidays):
    """
    Returns a list of working dates (datetime objects) for the given month and year,
    excluding weekends and public holidays.
    """
    num_days = calendar.monthrange(year, month)[1]
    all_dates = [datetime(year, month, day) for day in range(1, num_days + 1)]
    
    holiday_dates = set(pd.to_datetime(d).date() for d in public_holidays)
    working = [d for d in all_dates if d.weekday() < 5 and d.date() not in holiday_dates]
    return working

def matches_day_descriptor(date, descriptor, working_dates):
    """
    Checks if a given date matches a descriptor like '1st Tue' or 'Last Monday'.
    This updated version tries to match either the short weekday ('Mon') or
    the full weekday ('Monday') from the descriptor.

    Example descriptors:
      - '1st Mon'
      - '1st Monday'
      - 'Last Fri'
      - '2nd Wednesday'
    """
    try:
        parts = descriptor.split(maxsplit=1)  # e.g. ["1st", "Mon"] or ["1st", "Monday"]
        if len(parts) != 2:
            return False
        
        occurrence, weekday_code = parts
        occurrence = occurrence.strip().lower()  # e.g. "1st", "last"
        weekday_code_lc = weekday_code.strip().lower()  # e.g. "mon", "monday"
        
        # We'll compare both short and full forms of the date's weekday
        day_abbr_lc = date.strftime('%a').lower()    # e.g. "mon"
        day_full_lc = date.strftime('%A').lower()    # e.g. "monday"
        
        # If the descriptor's weekday doesn't match either short or full, return False
        if weekday_code_lc not in (day_abbr_lc, day_full_lc):
            return False
        
        # Collect all working dates in the same month with the same weekday
        same_weekday = []
        for wd in working_dates:
            if wd.month == date.month and wd.year == date.year:
                # Check if wd is the same weekday
                if wd.weekday() == date.weekday():
                    same_weekday.append(wd)
        
        # If "last", check if date is the final one in that list
        if occurrence == "last":
            return date == same_weekday[-1]
        else:
            # Attempt to parse "1st", "2nd", "3rd", "4th", etc.
            # We'll just grab the numeric part from occurrence
            numeric = ''.join([c for c in occurrence if c.isdigit()])  # e.g. "1"
            if not numeric.isdigit():
                return False
            idx = int(numeric) - 1  # zero-based
            if 0 <= idx < len(same_weekday):
                return date == same_weekday[idx]
            else:
                return False
    except Exception:
        return False

def generate_roster_schedule(excel_file):
    """
    Generates a team rostering schedule for a given month-year based on:
      - Named cells: 'OfficePercentage' and 'TargetMonthYear'
      - Excel tables: 'EmployeeData', 'SeatData', 'PublicHolidays',
                      'SubTeamOfficeDays', 'SpecialSubTeamDays', 'SeatPreferences'.
    """
    try:
        wb = load_workbook(excel_file)
        static_ws = wb["Static Data"]  # The sheet that contains the named cells & tables
        
        # 1. Read Named Cells
        office_percentage = get_named_cell_value(wb, "OfficePercentage")
        target_month_year = get_named_cell_value(wb, "TargetMonthYear")
        
        if not target_month_year:
            raise ValueError("TargetMonthYear is empty or not defined.")
        
        # Parse something like "Mar-25" => month=3, year=2025
        month_str, year_str = target_month_year.split("-")
        month = datetime.strptime(month_str, "%b").month
        if len(year_str) == 2:
            year = int("20" + year_str)
        else:
            year = int(year_str)
        
        # 2. Read Data from Excel Tables
        df_employees       = get_table_as_df(static_ws, "EmployeeData")
        df_seats           = get_table_as_df(static_ws, "SeatData")
        df_public_holidays = get_table_as_df(static_ws, "PublicHolidays")
        df_subteam_days    = get_table_as_df(static_ws, "SubTeamOfficeDays")
        df_special_days    = get_table_as_df(static_ws, "SpecialSubTeamDays")
        df_seat_pref       = get_table_as_df(static_ws, "SeatPreferences")
        
        # 3. Compute working days
        public_holiday_dates = df_public_holidays["Date"]
        working_dates = get_working_dates(year, month, public_holiday_dates)
        total_working_days = len(working_dates)
        
        required_days = round(total_working_days * (office_percentage / 100.0))
        
        # 4. Create dictionaries for easy lookups
        #    a) employee_remaining => how many days each employee still needs
        #    b) employee_names, emp_subteam_map => for name & sub-team lookups
        employee_remaining = {}
        for _, row in df_employees.iterrows():
            emp_id = row["EmployeeID"]
            employee_remaining[emp_id] = required_days
        
        employee_names = df_employees.set_index("EmployeeID")["EmployeeName"].to_dict()
        emp_subteam_map = df_employees.set_index("EmployeeID")["SubTeam"].to_dict()
        
        # 5. Prepare the schedule structure
        #    Key: date => Value: dict of seat_code => employee_id
        schedule = {day: {} for day in working_dates}
        
        # -----------------------------------------------------------------
        # A) Assign Fixed Seats
        # -----------------------------------------------------------------
        for _, seat_row in df_seats.iterrows():
            seat_code = seat_row["SeatCode"]
            seat_type = str(seat_row["SeatType"]).strip().lower()
            # Normalize seat days to lowercase
            seat_days = [d.strip().lower() for d in str(seat_row["Days"]).split(",")]
            
            assigned_emp = seat_row.get("AssignedEmployeeID")
            
            if seat_type == "fixed" and pd.notna(assigned_emp):
                for day in working_dates:
                    day_abbr_lc = day.strftime("%a").lower()   # e.g. "mon"
                    day_full_lc = day.strftime("%A").lower()   # e.g. "monday"
                    
                    # If either short or full name is in seat_days
                    if day_abbr_lc in seat_days or day_full_lc in seat_days:
                        schedule[day][seat_code] = assigned_emp
                        if employee_remaining.get(assigned_emp, 0) > 0:
                            employee_remaining[assigned_emp] -= 1
        
        # -----------------------------------------------------------------
        # B) Assign Flexible Seats
        # -----------------------------------------------------------------
        for day in working_dates:
            day_abbr_lc = day.strftime("%a").lower()
            day_full_lc = day.strftime("%A").lower()
            
            # Identify flexible seats that aren't already assigned
            available_seats = []
            for _, seat_row in df_seats.iterrows():
                seat_code = seat_row["SeatCode"]
                seat_type = str(seat_row["SeatType"]).strip().lower()
                seat_days = [d.strip().lower() for d in str(seat_row["Days"]).split(",")]
                
                if seat_type == "flexible":
                    if (day_abbr_lc in seat_days or day_full_lc in seat_days):
                        if seat_code not in schedule[day]:
                            available_seats.append(seat_code)
            
            # Check if this day is "special" for a sub-team
            special_subteam = None
            for _, sp_row in df_special_days.iterrows():
                descriptor = str(sp_row["DayDescriptor"]).strip()
                subteam = sp_row["SubTeam"]
                if matches_day_descriptor(day, descriptor, working_dates):
                    special_subteam = subteam
                    break
            
            # Build the list of employees eligible for that day
            if special_subteam:
                # Only employees from the special_subteam
                eligible_emps = df_employees[df_employees["SubTeam"] == special_subteam]["EmployeeID"].tolist()
            else:
                # Use SubTeamOfficeDays table
                eligible_emps = []
                for _, row_st in df_subteam_days.iterrows():
                    st = row_st["SubTeam"]
                    office_days = [x.strip().lower() for x in str(row_st["OfficeDays"]).split(",")]
                    
                    if day_abbr_lc in office_days or day_full_lc in office_days:
                        # Add employees from that sub-team
                        st_emps = df_employees[df_employees["SubTeam"] == st]["EmployeeID"].tolist()
                        eligible_emps.extend(st_emps)
                
                # Remove duplicates
                eligible_emps = list(set(eligible_emps))
            
            # Filter out those who no longer need to come in
            eligible_emps = [emp for emp in eligible_emps if employee_remaining.get(emp, 0) > 0]
            
            # Keep track of who we assign so we don't double-assign in the same day
            assigned_today = set()
            
            for seat_code in available_seats:
                # Check seat preferences first
                seat_pref_rows = df_seat_pref[df_seat_pref["SeatCode"] == seat_code]
                
                if not seat_pref_rows.empty:
                    pref_emp_ids = seat_pref_rows["EmployeeID"].tolist()
                    # Among pref_emp_ids, pick those who are eligible and not yet assigned
                    pref_candidates = [emp for emp in pref_emp_ids
                                       if emp in eligible_emps and emp not in assigned_today]
                    if pref_candidates:
                        chosen = random.choice(pref_candidates)
                        schedule[day][seat_code] = chosen
                        employee_remaining[chosen] -= 1
                        assigned_today.add(chosen)
                        continue
                
                # If no preferences or no pref candidates, assign randomly
                if eligible_emps:
                    avail_candidates = [emp for emp in eligible_emps if emp not in assigned_today]
                    if avail_candidates:
                        chosen = random.choice(avail_candidates)
                        schedule[day][seat_code] = chosen
                        employee_remaining[chosen] -= 1
                        assigned_today.add(chosen)
        
        # -----------------------------------------------------------------
        # C) Create or Overwrite the Output Sheet
        # -----------------------------------------------------------------
        if target_month_year in wb.sheetnames:
            out_ws = wb[target_month_year]
            # (Optional) Clear old data
            for row in out_ws.iter_rows(min_row=1, max_row=out_ws.max_row,
                                        min_col=1, max_col=out_ws.max_column):
                for cell in row:
                    cell.value = None
        else:
            out_ws = wb.create_sheet(title=target_month_year)
        
        seat_codes = df_seats["SeatCode"].tolist()
        headers = ["Date", "Day"] + seat_codes
        out_ws.append(headers)
        
        # Prepare color-coding for sub-teams
        unique_subteams = df_employees["SubTeam"].unique().tolist()
        color_palette = ["FFD7CC", "D7F7D7", "CCD7FF", "FFF2CC", "E2EFDA", "FCE4D6"]
        subteam_color = {st: color_palette[i % len(color_palette)] for i, st in enumerate(unique_subteams)}
        
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
        
        # Format header row
        header_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
        for cell in out_ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Color-code seat assignment cells by sub-team
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
    excel_filename = "TeamRoster.xlsx"  # Adjust as needed
    generate_roster_schedule(excel_filename)