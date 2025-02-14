import calendar
from datetime import datetime
import pandas as pd
from pulp import LpProblem, LpMaximize, LpVariable, lpSum, LpBinary, LpStatus
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# ------------------------------
# Helper functions for reading Excel
# ------------------------------

def get_named_cell_value(wb, cell_name):
    """Retrieves the value from a named cell in the workbook."""
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
    """Reads an Excel Table (ListObject) by its name on a given worksheet into a DataFrame."""
    for tbl in ws._tables:
        if tbl.name == table_name:
            ref = tbl.ref
            cells = ws[ref]
            data = [[cell.value for cell in row] for row in cells]
            return pd.DataFrame(data[1:], columns=data[0])
    raise ValueError(f"Table '{table_name}' not found on worksheet '{ws.title}'.")

def get_working_dates(year, month, public_holidays):
    """Returns a list of working dates (datetime objects) for the given month/year,
       excluding Saturdays, Sundays, and any public holidays (list of dates)."""
    num_days = calendar.monthrange(year, month)[1]
    all_dates = [datetime(year, month, d) for d in range(1, num_days + 1)]
    holiday_dates = set(pd.to_datetime(h).date() for h in public_holidays)
    working = [dt for dt in all_dates if dt.weekday() < 5 and dt.date() not in holiday_dates]
    return working

def parse_days_string(days_str):
    """
    Given a string like "Mon, Wed, Fri" or "Monday, Tuesday", return a set containing
    both the common 3-letter abbreviation and full name (all lowercase). For example,
    "Mon, Wed" becomes {"mon", "monday", "wed", "wednesday"}.
    """
    if not isinstance(days_str, str):
        return set()
    parts = [p.strip() for p in days_str.split(',')]
    day_set = set()
    for p in parts:
        p_l = p.lower()
        if p_l.startswith("mon"):
            day_set.update(["mon", "monday"])
        elif p_l.startswith("tue"):
            day_set.update(["tue", "tuesday"])
        elif p_l.startswith("wed"):
            day_set.update(["wed", "wednesday"])
        elif p_l.startswith("thu"):
            day_set.update(["thu", "thursday"])
        elif p_l.startswith("fri"):
            day_set.update(["fri", "friday"])
    return day_set

# ------------------------------
# Functions for day descriptor matching
# ------------------------------

def parse_day_descriptor(descriptor):
    """
    Parses descriptors like "1st Working Tuesday" or "Last Fri" and returns a tuple:
    (occurrence, weekday_str) where occurrence is a string (e.g., "1st" or "last")
    and weekday_str is normalized (e.g., "mon" or "tuesday").
    If parsing fails, returns (None, None).
    """
    descriptor = descriptor.strip().lower()
    tokens = descriptor.split()
    valid_occurrences = {"1st", "2nd", "3rd", "4th", "5th", "last"}
    valid_short_days  = ["mon", "tue", "wed", "thu", "fri"]
    valid_full_days   = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    occ, wday = None, None
    for token in tokens:
        if token in valid_occurrences:
            occ = token
        else:
            for sd in valid_short_days:
                if token.startswith(sd):
                    wday = sd
                    break
            for fd in valid_full_days:
                if token == fd:
                    wday = fd
                    break
    if not occ or not wday:
        return (None, None)
    return (occ, wday)

def is_day_descriptor_match(date_obj, descriptor, working_dates):
    """
    Returns True if the date_obj (a working date) matches the descriptor
    (e.g., "1st Tuesday", "Last Fri") based on the list of working_dates.
    """
    occ, wday = parse_day_descriptor(descriptor)
    if not occ or not wday:
        return False
    # Map weekday string to integer (Monday=0,...,Friday=4)
    short_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4}
    full_map  = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4}
    if wday in short_map:
        needed_wd = short_map[wday]
    elif wday in full_map:
        needed_wd = full_map[wday]
    else:
        return False
    if date_obj.weekday() != needed_wd:
        return False
    same_wd_dates = [d for d in working_dates if d.year == date_obj.year and d.month == date_obj.month and d.weekday() == needed_wd]
    same_wd_dates.sort()
    if not same_wd_dates:
        return False
    if occ == "last":
        return date_obj == same_wd_dates[-1]
    else:
        digit_part = "".join(c for c in occ if c.isdigit())
        if not digit_part.isdigit():
            return False
        idx = int(digit_part) - 1
        if 0 <= idx < len(same_wd_dates):
            return date_obj == same_wd_dates[idx]
        else:
            return False

# ------------------------------
# ILP Model – Global Rostering Solver
# ------------------------------

def generate_roster_schedule_ilp(excel_file):
    """
    This function builds and solves a global ILP that assigns seats over the entire month
    ensuring every employee meets their required days (if feasible). Fixed seats are strictly enforced.
    Special sub-team days (from SpecialSubTeamDays) are exclusive, but sub-team office days (from SubTeamOfficeDays)
    only yield a bonus (priority) without exclusion. Seat preferences are also rewarded.
    The final output is written in a column-oriented format:
       - Column A: "Employee Name"
       - Row 1 (columns B onward): Dates (YYYY-MM-DD)
       - Row 2 (columns B onward): Day-of-week (e.g., Mon, Tue)
       - Rows 3 onward: Each employee’s row with the assigned seat code for that day (or blank if not assigned).
    """
    wb = load_workbook(excel_file)
    static_ws = wb["Static Data"]
    
    # Read named cells
    office_percentage = get_named_cell_value(wb, "OfficePercentage")  # Already in [0,1]
    target_month_year = get_named_cell_value(wb, "TargetMonthYear")   # e.g., "Mar-25"
    month_str, year_str = target_month_year.split("-")
    month = datetime.strptime(month_str, "%b").month
    year = int("20" + year_str) if len(year_str) == 2 else int(year_str)
    
    # Read tables
    df_employees       = get_table_as_df(static_ws, "EmployeeData")
    df_seats           = get_table_as_df(static_ws, "SeatData")
    df_public_holidays = get_table_as_df(static_ws, "PublicHolidays")
    df_subteam_days    = get_table_as_df(static_ws, "SubTeamOfficeDays")
    df_special_days    = get_table_as_df(static_ws, "SpecialSubTeamDays")
    df_seat_pref       = get_table_as_df(static_ws, "SeatPreferences")
    
    # Build lists
    employees = df_employees["EmployeeID"].tolist()
    seats = df_seats["SeatCode"].tolist()
    
    # Working dates (sorted)
    working_dates = get_working_dates(year, month, df_public_holidays["Date"])
    working_dates.sort()
    total_wd = len(working_dates)
    
    # Each employee must attend a minimum number of days
    required_days = {e: round(total_wd * office_percentage) for e in employees}
    
    # Map employee details (we output name only)
    emp_names = dict(zip(df_employees["EmployeeID"], df_employees["EmployeeName"]))
    emp_subteam = dict(zip(df_employees["EmployeeID"], df_employees["SubTeam"]))
    
    # For seat preferences, assign a bonus if an employee prefers a seat.
    # (Bonus value can be tuned.)
    seat_pref_bonus = {}
    for _, row in df_seat_pref.iterrows():
        e = row["EmployeeID"]
        s = row["SeatCode"]
        seat_pref_bonus[(e, s)] = 10  # bonus for matching preference
    
    # Build sub-team designated days bonus from SubTeamOfficeDays (non-exclusive)
    # For each sub-team, get the set of day tokens (e.g., "mon", "monday", etc.)
    subteam_days_map = {}
    for _, row in df_subteam_days.iterrows():
        st = row["SubTeam"]
        ds = parse_days_string(row["OfficeDays"])
        subteam_days_map.setdefault(st, set()).update(ds)
    
    # Bonus if an employee is assigned on a day that is designated for their sub-team.
    subteam_bonus = 5
    fill_bonus = 1  # bonus for simply filling a seat
    
    # Determine seat availability by day
    # For each seat s and each working date d, check if d is allowed based on SeatData["Days"]
    seat_day_avail = {}
    for _, srow in df_seats.iterrows():
        s_code = srow["SeatCode"]
        allowed_days = parse_days_string(srow["Days"])
        for d in working_dates:
            d_abbr = d.strftime("%a").lower()
            d_full = d.strftime("%A").lower()
            seat_day_avail[(s_code, d)] = (d_abbr in allowed_days or d_full in allowed_days)
    
    # Fixed seat assignments: for seats with SeatType "fixed" and an AssignedEmployeeID, force assignment on allowed days.
    fixed_assign = {}
    for _, row in df_seats.iterrows():
        if str(row["SeatType"]).strip().lower() == "fixed":
            assigned_emp = row.get("AssignedEmployeeID")
            if pd.notna(assigned_emp):
                s_code = row["SeatCode"]
                allowed_days = parse_days_string(row["Days"])
                for d in working_dates:
                    d_abbr = d.strftime("%a").lower()
                    d_full = d.strftime("%A").lower()
                    if d_abbr in allowed_days or d_full in allowed_days:
                        fixed_assign[(s_code, d)] = assigned_emp
    
    # Build the ILP model
    model = LpProblem("GlobalTeamRostering", LpMaximize)
    
    # Decision variables: x[e,s,d] = 1 if employee e is assigned seat s on day d, else 0.
    x = {}
    for e in employees:
        for s in seats:
            for d in working_dates:
                var_name = f"x_{e}_{s}_{d.strftime('%d')}"
                x[(e,s,d)] = LpVariable(var_name, cat=LpBinary)
    
    # Constraint 1: Each seat gets at most one occupant per day.
    for s in seats:
        for d in working_dates:
            model += lpSum(x[(e,s,d)] for e in employees) <= 1, f"SeatOccupancy_{s}_{d.strftime('%Y%m%d')}"
    
    # Constraint 2: Each employee occupies at most one seat per day.
    for e in employees:
        for d in working_dates:
            model += lpSum(x[(e,s,d)] for s in seats) <= 1, f"EmployeeOneSeat_{e}_{d.strftime('%Y%m%d')}"
    
    # Constraint 3: Each employee must meet their required days.
    for e in employees:
        model += lpSum(x[(e,s,d)] for s in seats for d in working_dates) >= required_days[e], f"RequiredDays_{e}"
    
    # Constraint 4: Fixed seats must be enforced.
    for (s_code, d), e_fixed in fixed_assign.items():
        model += x[(e_fixed, s_code, d)] == 1, f"FixedSeat_{s_code}_{d.strftime('%Y%m%d')}"
        for e in employees:
            if e != e_fixed:
                model += x[(e,s_code,d)] == 0, f"FixedSeatZero_{s_code}_{d.strftime('%Y%m%d')}_{e}"
    
    # Constraint 5: Special sub-team days (from SpecialSubTeamDays) are exclusive.
    # For each working day, if it matches a descriptor in SpecialSubTeamDays,
    # then only employees of that sub-team can be assigned.
    for d in working_dates:
        special_st = None
        for _, row in df_special_days.iterrows():
            descriptor = str(row["DayDescriptor"]).strip()
            if is_day_descriptor_match(d, descriptor, working_dates):
                special_st = row["SubTeam"]
                break
        if special_st is not None:
            for e in employees:
                if emp_subteam[e] != special_st:
                    for s in seats:
                        model += x[(e,s,d)] == 0, f"SpecialExcl_{e}_{s}_{d.strftime('%Y%m%d')}"
    
    # Constraint 6: A seat can only be assigned on a day if the seat is available on that day.
    for s in seats:
        for d in working_dates:
            if not seat_day_avail[(s,d)]:
                for e in employees:
                    model += x[(e,s,d)] == 0, f"SeatNotAvail_{s}_{d.strftime('%Y%m%d')}_{e}"
    
    # Build the objective function.
    # For each (e,s,d): reward = (seat preference bonus) + (sub-team bonus if d is designated for e's sub-team) + (fill bonus)
    obj_terms = []
    for e in employees:
        e_st = emp_subteam[e]
        for s in seats:
            pref_bonus = seat_pref_bonus.get((e,s), 0)
            for d in working_dates:
                d_abbr = d.strftime("%a").lower()
                d_full = d.strftime("%A").lower()
                st_bonus = 0
                if e_st in subteam_days_map:
                    if d_abbr in subteam_days_map[e_st] or d_full in subteam_days_map[e_st]:
                        st_bonus = subteam_bonus
                bonus = pref_bonus + st_bonus + fill_bonus
                obj_terms.append(bonus * x[(e,s,d)])
    
    model += lpSum(obj_terms), "TotalBonus"
    
    # Solve the ILP
    model.solve()
    if LpStatus[model.status] != "Optimal":
        print("No feasible solution found or the solver did not converge to an optimal solution.")
        return
    
    # Extract solution into a mapping: for each employee and each day, record the seat code assigned (if any)
    emp_day_assignment = {(e,d): None for e in employees for d in working_dates}
    for e in employees:
        for d in working_dates:
            for s in seats:
                if x[(e,s,d)].varValue == 1:
                    emp_day_assignment[(e,d)] = s
                    break  # only one seat per day per employee
    
    # ------------------------------
    # Output: Create a column-oriented sheet.
    # We build a table where:
    #  - Column A header: "Employee Name"
    #  - Columns B onward: each column corresponds to a working date.
    #    Row1: the date (YYYY-MM-DD), Row2: day-of-week.
    #  - Rows 3 onward: one row per employee. The first cell is the employee name,
    #    then each cell in that row is the seat code assigned on that date (or blank).
    # ------------------------------
    
    out_sheet_name = target_month_year
    if out_sheet_name in wb.sheetnames:
        out_ws = wb[out_sheet_name]
        # Clear existing data
        for row in out_ws.iter_rows(min_row=1, max_row=out_ws.max_row, min_col=1, max_col=out_ws.max_column):
            for cell in row:
                cell.value = None
    else:
        out_ws = wb.create_sheet(title=out_sheet_name)
    
    # Write header rows:
    # Row 1: Column A = "Employee Name", then columns B onward = date (e.g., "2025-03-04")
    out_ws.cell(row=1, column=1).value = "Employee Name"
    for j, d in enumerate(working_dates, start=2):
        out_ws.cell(row=1, column=j).value = d.strftime("%Y-%m-%d")
    # Row 2: Column A blank, then day-of-week (e.g., "Wed")
    out_ws.cell(row=2, column=1).value = ""
    for j, d in enumerate(working_dates, start=2):
        out_ws.cell(row=2, column=j).value = d.strftime("%a")
    
    # Write employee rows (one row per employee)
    for i, e in enumerate(employees, start=3):
        out_ws.cell(row=i, column=1).value = emp_names[e]
        for j, d in enumerate(working_dates, start=2):
            seat_assigned = emp_day_assignment.get((e,d), None)
            out_ws.cell(row=i, column=j).value = seat_assigned if seat_assigned else ""
    
    # Apply formatting (bold headers, center alignment)
    header_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
    for cell in out_ws[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for cell in out_ws[2]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    # Adjust column widths
    for col in out_ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value and isinstance(cell.value, str):
                max_len = max(max_len, len(cell.value))
        out_ws.column_dimensions[col_letter].width = max_len + 2
    
    wb.save(excel_file)
    print("Global ILP schedule generated successfully.")

if __name__ == "__main__":
    excel_filename = "TeamRoster.xlsx"  # Update the filename/path as needed
    generate_roster_schedule_ilp(excel_filename)