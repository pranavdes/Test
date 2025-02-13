import calendar
import random
from datetime import datetime
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

def get_named_range_as_df(wb, range_name):
    """
    Reads a named range from the workbook and returns a DataFrame.
    Assumes that the first row in the range is the header.
    """
    try:
        defined_range = wb.defined_names[range_name]
        for title, coord in defined_range.destinations:
            ws = wb[title]
            cells = ws[coord]
            data = [[cell.value for cell in row] for row in cells]
            df = pd.DataFrame(data[1:], columns=data[0])
            return df
    except Exception as e:
        raise ValueError(f"Error reading named range '{range_name}': {e}")
    return None

def get_named_cell_value(wb, cell_name):
    """
    Retrieves the value from a single-cell named range.
    """
    try:
        defined_range = wb.defined_names[cell_name]
        for title, coord in defined_range.destinations:
            ws = wb[title]
            return ws[coord].value
    except Exception as e:
        raise ValueError(f"Error reading named cell '{cell_name}': {e}")
    return None

def get_working_dates(year, month, public_holidays):
    """
    Returns a list of working dates (datetime objects) for the given month and year,
    excluding weekends and public holidays.
    """
    num_days = calendar.monthrange(year, month)[1]
    all_dates = [datetime(year, month, day) for day in range(1, num_days + 1)]
    public_holiday_dates = [pd.to_datetime(d).date() for d in public_holidays]
    working = [d for d in all_dates if d.weekday() < 5 and d.date() not in public_holiday_dates]
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
        occurrence, weekday_code = parts
        day_abbr = date.strftime('%a')
        if not day_abbr.lower().startswith(weekday_code.lower()):
            return False
        same_weekday = [d for d in working_dates if d.month == date.month and d.weekday() == date.weekday()]
        if occurrence.lower() == "last":
            return date == same_weekday[-1]
        else:
            num = int(occurrence[0])
            if len(same_weekday) >= num:
                return date == same_weekday[num - 1]
            else:
                return False
    except Exception:
        return False

def generate_roster_schedule(excel_file):
    """
    Generates a team rostering schedule for a given month-year based on the data in the
    'Static Data' sheet. The new sheet is named after the month-year (e.g. 'Mar-25').
    The output now includes both Employee ID and Employee Name for each seat assignment.
    """
    try:
        wb = load_workbook(excel_file)
        static_ws = wb["Static Data"]

        # Read source tables using named ranges
        df_employees       = get_named_range_as_df(wb, "EmployeeData")
        df_seats           = get_named_range_as_df(wb, "SeatData")
        df_public_holidays = get_named_range_as_df(wb, "PublicHolidays")
        df_subteam_days    = get_named_range_as_df(wb, "SubTeamOfficeDays")
        df_special_days    = get_named_range_as_df(wb, "SpecialSubTeamDays")
        df_seat_pref       = get_named_range_as_df(wb, "SeatPreferences")
        office_percentage  = get_named_cell_value(wb, "OfficePercentage")
        
        # Read the target month-year from a named cell 'TargetMonthYear' (e.g., "Mar-25")
        target_month_year = get_named_cell_value(wb, "TargetMonthYear")
        if not target_month_year:
            raise ValueError("Target month-year not specified (named cell 'TargetMonthYear' missing).")
        month_str, year_str = target_month_year.split("-")
        month = datetime.strptime(month_str, "%b").month
        year = int("20" + year_str) if len(year_str) == 2 else int(year_str)
        
        # Get working dates for the month
        working_dates = get_working_dates(year, month, df_public_holidays["Date"])
        total_working_days = len(working_dates)
        
        # Calculate required in-office days per employee (rounded to nearest whole number)
        required_days = round(total_working_days * (office_percentage / 100))
        employee_remaining = {emp: required_days for emp in df_employees["EmployeeID"]}
        
        # Mapping for employee names and sub-teams
        employee_names = df_employees.set_index("EmployeeID")["EmployeeName"].to_dict()
        emp_subteam_map = df_employees.set_index("EmployeeID")["SubTeam"].to_dict()
        
        schedule = {d: {} for d in working_dates}

        # -------------------------
        # 1. Assign Fixed Seats
        # -------------------------
        for _, seat in df_seats.iterrows():
            seat_code = seat["SeatCode"]
            seat_type = str(seat["SeatType"]).strip().lower()
            days_list = [d.strip() for d in str(seat["Days"]).split(",")]
            assigned_emp = seat.get("AssignedEmployeeID")
            if seat_type == "fixed" and pd.notna(assigned_emp):
                for d in working_dates:
                    day_abbr = d.strftime("%a")
                    if day_abbr in days_list or d.strftime("%A") in days_list:
                        schedule[d][seat_code] = assigned_emp
                        if employee_remaining.get(assigned_emp, 0) > 0:
                            employee_remaining[assigned_emp] -= 1

        # -------------------------
        # 2. Assign Flexible Seats
        # -------------------------
        for d in working_dates:
            day_abbr = d.strftime("%a")
            available_seats = []
            for _, seat in df_seats.iterrows():
                seat_code = seat["SeatCode"]
                seat_type = str(seat["SeatType"]).strip().lower()
                days_list = [x.strip() for x in str(seat["Days"]).split(",")]
                if seat_type == "flexible" and (day_abbr in days_list or d.strftime("%A") in days_list):
                    if seat_code not in schedule[d]:
                        available_seats.append(seat_code)
            
            special_subteam = None
            for _, row in df_special_days.iterrows():
                descriptor = str(row["DayDescriptor"]).strip()
                subteam = row["SubTeam"]
                if matches_day_descriptor(d, descriptor, working_dates):
                    special_subteam = subteam
                    break

            if special_subteam:
                eligible = df_employees[df_employees["SubTeam"] == special_subteam]["EmployeeID"].tolist()
            else:
                eligible = []
                for _, row in df_subteam_days.iterrows():
                    subteam = row["SubTeam"]
                    office_days = [x.strip() for x in str(row["OfficeDays"]).split(",")]
                    if day_abbr in office_days or d.strftime("%A") in office_days:
                        eligible.extend(df_employees[df_employees["SubTeam"] == subteam]["EmployeeID"].tolist())
                eligible = list(set(eligible))
            
            eligible = [emp for emp in eligible if employee_remaining.get(emp, 0) > 0]

            assigned_today = set()
            for seat in available_seats:
                pref_rows = df_seat_pref[df_seat_pref["SeatCode"] == seat]
                if not pref_rows.empty:
                    prefs = pref_rows["EmployeeID"].tolist()
                    prefs = [p for p in prefs if p in eligible and p not in assigned_today]
                    if prefs:
                        chosen = random.choice(prefs)
                        schedule[d][seat] = chosen
                        employee_remaining[chosen] -= 1
                        assigned_today.add(chosen)
                        continue
                if eligible:
                    avail_candidates = [emp for emp in eligible if emp not in assigned_today]
                    if avail_candidates:
                        chosen = random.choice(avail_candidates)
                        schedule[d][seat] = chosen
                        employee_remaining[chosen] -= 1
                        assigned_today.add(chosen)

        # -------------------------
        # 3. Create the Output Sheet with Formatting
        # -------------------------
        if target_month_year in wb.sheetnames:
            out_ws = wb[target_month_year]
        else:
            out_ws = wb.create_sheet(title=target_month_year)
        
        # Updated headers now include: Date, Day, and one column per Seat.
        headers = ["Date", "Day"] + df_seats["SeatCode"].tolist()
        out_ws.append(headers)
        
        unique_subteams = df_employees["SubTeam"].unique().tolist()
        color_palette = ["FFD7CC", "D7F7D7", "CCD7FF", "FFF2CC", "E2EFDA", "FCE4D6"]
        subteam_color = {st: color_palette[i % len(color_palette)] for i, st in enumerate(unique_subteams)}
        
        sorted_dates = sorted(schedule.keys())
        for d in sorted_dates:
            row = [d.strftime("%Y-%m-%d"), d.strftime("%a")]
            for seat in df_seats["SeatCode"].tolist():
                emp = schedule[d].get(seat, "")
                if emp:
                    # Lookup employee name and output in "ID - Name" format.
                    emp_name = employee_names.get(emp, "")
                    row.append(f"{emp} - {emp_name}")
                else:
                    row.append("")
            out_ws.append(row)
        
        # Format header row.
        header_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
        for cell in out_ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Color-code seat assignment cells based on the employee's sub-team.
        for row in out_ws.iter_rows(min_row=2, min_col=3, max_col=out_ws.max_column):
            for cell in row:
                if cell.value:
                    # Extract employee ID from "EmployeeID - EmployeeName" format.
                    emp_id = cell.value.split(" - ")[0].strip()
                    if emp_id in emp_subteam_map:
                        st = emp_subteam_map[emp_id]
                        fill_color = subteam_color.get(st, "FFFFFF")
                        cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
                        cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Adjust column widths for clarity.
        for col in out_ws.columns:
            max_length = 0
            column = get_column_letter(col[0].column)
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            out_ws.column_dimensions[column].width = max_length + 2
        
        wb.save(excel_file)
        print("Roster schedule generated successfully.")
    
    except Exception as e:
        print(f"Error generating schedule: {e}")

if __name__ == "__main__":
    excel_filename = "TeamRoster.xlsx"
    generate_roster_schedule(excel_filename)