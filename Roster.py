import calendar
from datetime import datetime
import pandas as pd
from pulp import LpProblem, LpMaximize, LpVariable, lpSum, LpBinary, LpInteger, LpStatus
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# ------------------------------
# Helper functions for Excel I/O
# ------------------------------

def get_named_cell_value(wb, cell_name):
    """Retrieves the value from a named cell in the workbook."""
    try:
        defined_range = wb.defined_names[cell_name]
        for title, coord in defined_range.destinations:
            ws = wb[title]
            return ws[coord].value
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
    """Returns a sorted list of working dates (datetime objects) for the month/year,
       excluding weekends and any public holidays (which are dates)."""
    num_days = calendar.monthrange(year, month)[1]
    all_dates = [datetime(year, month, d) for d in range(1, num_days+1)]
    holiday_dates = set(pd.to_datetime(h).date() for h in public_holidays)
    working = [dt for dt in all_dates if dt.weekday() < 5 and dt.date() not in holiday_dates]
    return sorted(working)

def parse_days_string(days_str):
    """
    Given a string like "Mon, Wed, Fri" or "Monday, Tuesday", return a set containing
    both the common 3-letter abbreviation and full name (all in lowercase).
    E.g., "Mon, Wed" -> {"mon","monday","wed","wednesday"}
    """
    if not isinstance(days_str, str):
        return set()
    parts = [p.strip() for p in days_str.split(',')]
    day_set = set()
    for p in parts:
        lp = p.lower()
        if lp.startswith("mon"):
            day_set.update(["mon","monday"])
        elif lp.startswith("tue"):
            day_set.update(["tue","tuesday"])
        elif lp.startswith("wed"):
            day_set.update(["wed","wednesday"])
        elif lp.startswith("thu"):
            day_set.update(["thu","thursday"])
        elif lp.startswith("fri"):
            day_set.update(["fri","friday"])
    return day_set

# ------------------------------
# Functions for day descriptor matching
# ------------------------------

def parse_day_descriptor(descriptor):
    """
    Parses a descriptor like "1st Working Tuesday" or "Last Fri"
    and returns a tuple (occurrence, weekday) where occurrence is e.g. "1st" or "last"
    and weekday is normalized (e.g., "mon" or "tuesday"). Returns (None, None) if parsing fails.
    """
    descriptor = descriptor.strip().lower()
    tokens = descriptor.split()
    valid_occurrences = {"1st", "2nd", "3rd", "4th", "5th", "last"}
    valid_short_days = {"mon", "tue", "wed", "thu", "fri"}
    occ, wday = None, None
    for token in tokens:
        if token in valid_occurrences:
            occ = token
        else:
            for day in valid_short_days:
                if token.startswith(day):
                    wday = day
                    break
    return (occ, wday) if occ and wday else (None, None)

def is_day_descriptor_match(date_obj, descriptor, working_dates):
    """
    Returns True if date_obj matches the descriptor (e.g., "1st Tuesday" or "Last Fri")
    according to the list of working_dates.
    """
    occ, wday = parse_day_descriptor(descriptor)
    if not occ or not wday:
        return False
    # Map weekday to integer (Monday=0, ..., Friday=4)
    day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4}
    needed_wd = day_map.get(wday)
    if date_obj.weekday() != needed_wd:
        return False
    same_wd = [d for d in working_dates if d.year == date_obj.year and d.month == date_obj.month and d.weekday() == needed_wd]
    same_wd.sort()
    if occ == "last":
        return date_obj == same_wd[-1] if same_wd else False
    else:
        # e.g., "1st" means index 0
        try:
            idx = int(''.join([c for c in occ if c.isdigit()])) - 1
        except:
            return False
        return date_obj == same_wd[idx] if 0 <= idx < len(same_wd) else False

# ------------------------------
# Global ILP Rostering Solver
# ------------------------------

def generate_roster_schedule_ilp(excel_file, designated_min=3, big_penalty=1000):
    """
    Builds and solves a global ILP model that assigns seats over the month so that:
      1. Every employee meets their overall threshold (required_days).
      2. Fixed seats are forced.
      3. On each day, available seats are filled.
      4. On designated days (from SubTeamOfficeDays) employees receive a bonus.
         In addition, for each employee in a sub-team with designated days,
         we require (with a slack variable) that they get at least 'designated_min'
         assignments on designated days (the slack is heavily penalized in the objective).
      5. On special days (from SpecialSubTeamDays), extra bonus is given to employees
         in the special sub-team—but remaining seats may go to others.
    The objective maximizes seat-preference, designated-day, and fill bonuses,
    while penalizing any shortfall in designated-day assignments.
    The final output is written in a new sheet (named by TargetMonthYear) in a column-oriented format:
      - Column A: Employee Name
      - Row 1 (columns B onward): Date (YYYY-MM-DD)
      - Row 2 (columns B onward): Day-of-week
      - Rows 3 onward: For each employee, the seat code assigned on that day (or blank).
    """
    # Load workbook and static data sheet
    wb = load_workbook(excel_file)
    static_ws = wb["Static Data"]
    
    # Read named cells
    office_percentage = get_named_cell_value(wb, "OfficePercentage")  # already in [0,1]
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
    
    # Build lists of employees and seats
    employees = df_employees["EmployeeID"].tolist()
    seats = df_seats["SeatCode"].tolist()
    
    # Working dates (sorted)
    working_dates = get_working_dates(year, month, df_public_holidays["Date"])
    total_wd = len(working_dates)
    
    # Each employee's overall required days
    req_days = {e: round(total_wd * office_percentage) for e in employees}
    
    # Map employee details (we output name only)
    emp_names = dict(zip(df_employees["EmployeeID"], df_employees["EmployeeName"]))
    emp_subteam = dict(zip(df_employees["EmployeeID"], df_employees["SubTeam"]))
    
    # Compute designated days for each sub-team from SubTeamOfficeDays:
    # For each row, we have a sub-team and a string of office days.
    designated_map = {}  # subteam -> set of day tokens (e.g., {"mon", "wed"})
    for _, row in df_subteam_days.iterrows():
        st = row["SubTeam"]
        days_set = parse_days_string(row["OfficeDays"])
        designated_map.setdefault(st, set()).update(days_set)
    # For each employee e, if their sub-team appears in designated_map, then
    # D_des(e) = { d in working_dates : d's abbreviated or full day is in designated_map[emp_subteam[e]] }
    designated_days = {}
    for e in employees:
        st = emp_subteam[e]
        if st in designated_map:
            designated_days[e] = {d for d in working_dates if d.strftime("%a").lower() in designated_map[st]
                                    or d.strftime("%A").lower() in designated_map[st]}
        else:
            designated_days[e] = set()  # no designated days
    
    # For special days (from df_special_days), we allow an extra bonus for employees in that sub-team.
    # For each working date, check if it matches any descriptor; if so, let special[d] = T (sub-team)
    special = {}
    for d in working_dates:
        for _, row in df_special_days.iterrows():
            desc = str(row["DayDescriptor"]).strip()
            if is_day_descriptor_match(d, desc, working_dates):
                special[d] = row["SubTeam"]
                break  # assume at most one special per day
    
    # Seat preference bonus: if (e,s) appears in SeatPreferences, assign bonus.
    pref_bonus = {}
    for _, row in df_seat_pref.iterrows():
        e = row["EmployeeID"]
        s = row["SeatCode"]
        pref_bonus[(e, s)] = 10  # adjust as desired
    
    # Other bonus parameters
    fill_bonus = 1
    designated_bonus = 5  # bonus if assignment occurs on a designated day
    special_bonus = 20    # extra bonus if on a special day and employee is in the special sub-team
    
    # For each seat, determine on which days it is available based on its "Days" field.
    seat_available = {}
    for _, srow in df_seats.iterrows():
        s_code = srow["SeatCode"]
        avail_set = parse_days_string(srow["Days"])
        for d in working_dates:
            d_abbr = d.strftime("%a").lower()
            d_full = d.strftime("%A").lower()
            seat_available[(s_code, d)] = (d_abbr in avail_set or d_full in avail_set)
    
    # Fixed seat assignments: For seats with type "fixed" and an AssignedEmployeeID, force that assignment on allowed days.
    fixed = {}
    for _, row in df_seats.iterrows():
        if str(row["SeatType"]).strip().lower() == "fixed":
            assigned = row.get("AssignedEmployeeID")
            if pd.notna(assigned):
                s_code = row["SeatCode"]
                avail_set = parse_days_string(row["Days"])
                for d in working_dates:
                    d_abbr = d.strftime("%a").lower()
                    d_full = d.strftime("%A").lower()
                    if d_abbr in avail_set or d_full in avail_set:
                        fixed[(s_code, d)] = assigned
    
    # ------------------------------
    # Build the ILP model
    # ------------------------------
    model = LpProblem("GlobalTeamRostering", LpMaximize)
    
    # Decision variables: x[e,s,d] = 1 if employee e is assigned seat s on day d.
    x = {}
    for e in employees:
        for s in seats:
            for d in working_dates:
                var_name = f"x_{e}_{s}_{d.strftime('%d')}"
                x[(e,s,d)] = LpVariable(var_name, cat=LpBinary)
    
    # For each employee with designated days, create a slack variable z_e (integer, >=0)
    z = {}
    for e in employees:
        # Only if there are designated days for e
        if designated_days[e]:
            var_name = f"z_{e}"
            z[e] = LpVariable(var_name, lowBound=0, cat=LpInteger)
    
    # ---- Constraints ----
    # 1. Each seat can be occupied by at most one employee per day.
    for s in seats:
        for d in working_dates:
            model += lpSum(x[(e,s,d)] for e in employees) <= 1, f"Seat_{s}_{d.strftime('%Y%m%d')}_occupancy"
    
    # 2. Each employee can use at most one seat per day.
    for e in employees:
        for d in working_dates:
            model += lpSum(x[(e,s,d)] for s in seats) <= 1, f"Employee_{e}_{d.strftime('%Y%m%d')}_oneSeat"
    
    # 3. Every employee must meet their overall quota.
    for e in employees:
        model += lpSum(x[(e,s,d)] for s in seats for d in working_dates) >= req_days[e], f"Quota_{e}"
    
    # 4. For each employee with designated days, enforce a minimum number of assignments on those days.
    #    sum_{d in designated_days(e), s in S} x[e,s,d] + z_e >= designated_min.
    #    The slack variable z_e will be penalized in the objective.
    for e in employees:
        if designated_days[e]:
            model += lpSum(x[(e,s,d)] for s in seats for d in designated_days[e]) + z[e] >= designated_min, f"Designated_{e}"
    
    # 5. Fixed seat assignments: For each (s,d) in fixed, force x[assigned,s,d] = 1 and others = 0.
    for (s,d), e_fixed in fixed.items():
        model += x[(e_fixed, s, d)] == 1, f"Fixed_{s}_{d.strftime('%Y%m%d')}"
        for e in employees:
            if e != e_fixed:
                model += x[(e,s,d)] == 0, f"FixedZero_{e}_{s}_{d.strftime('%Y%m%d')}"
    
    # 6. Seat availability: If a seat is not available on a day, force x[e,s,d] = 0.
    for s in seats:
        for d in working_dates:
            if not seat_available[(s,d)]:
                for e in employees:
                    model += x[(e,s,d)] == 0, f"NotAvail_{e}_{s}_{d.strftime('%Y%m%d')}"
    
    # 7. (Special days) – We now do NOT force exclusivity.
    # Instead, we add an extra bonus (in the objective) for assignments on a special day to employees in the designated sub-team.
    # (No hard constraint here.)
    
    # ---- Objective Function ----
    # For each assignment x[e,s,d], add:
    #   - fill_bonus (always)
    #   - seat preference bonus if applicable
    #   - designated bonus if d is in designated_days(e)
    #   - special bonus if d is a special day and emp_subteam[e] equals special[d]
    bonus_terms = []
    for e in employees:
        for s in seats:
            for d in working_dates:
                bonus = fill_bonus
                if (e,s) in pref_bonus:
                    bonus += pref_bonus[(e,s)]
                # designated bonus: if d is in e's designated set
                if d in designated_days[e]:
                    bonus += designated_bonus
                # special bonus: if d is special and e is in that sub-team
                if d in special and emp_subteam[e] == special[d]:
                    bonus += special_bonus
                bonus_terms.append(bonus * x[(e,s,d)])
    # Now subtract a heavy penalty for slack in designated-day constraint
    penalty_terms = []
    for e in z:
        penalty_terms.append(big_penalty * z[e])
    model += lpSum(bonus_terms) - lpSum(penalty_terms), "TotalObjective"
    
    # ------------------------------
    # Solve the ILP
    # ------------------------------
    model.solve()
    if LpStatus[model.status] != "Optimal":
        print("No feasible solution found or solver did not converge to an optimal solution.")
        return
    
    # ------------------------------
    # Extract solution: For each employee and day, determine the seat assigned (if any)
    # ------------------------------
    emp_day_assign = {(e,d): None for e in employees for d in working_dates}
    for e in employees:
        for d in working_dates:
            for s in seats:
                if x[(e,s,d)].varValue == 1:
                    emp_day_assign[(e,d)] = s
                    break
    
    # ------------------------------
    # Build Output Sheet in column-oriented format:
    # Columns: Column A: "Employee Name"; Columns B onward: each working date.
    # Row 1: date (YYYY-MM-DD); Row 2: day-of-week.
    # Rows 3 onward: one row per employee; each cell shows the seat code (or blank).
    # ------------------------------
    out_sheet_name = target_month_year
    if out_sheet_name in wb.sheetnames:
        out_ws = wb[out_sheet_name]
        # Clear existing data:
        for row in out_ws.iter_rows(min_row=1, max_row=out_ws.max_row, min_col=1, max_col=out_ws.max_column):
            for cell in row:
                cell.value = None
    else:
        out_ws = wb.create_sheet(title=out_sheet_name)
    
    # Write header rows
    out_ws.cell(row=1, column=1).value = "Employee Name"
    for j, d in enumerate(working_dates, start=2):
        out_ws.cell(row=1, column=j).value = d.strftime("%Y-%m-%d")
        out_ws.cell(row=2, column=j).value = d.strftime("%a")
    out_ws.cell(row=2, column=1).value = ""
    
    # Write one row per employee (starting from row 3)
    for i, e in enumerate(employees, start=3):
        out_ws.cell(row=i, column=1).value = emp_names[e]
        for j, d in enumerate(working_dates, start=2):
            seat_code = emp_day_assign.get((e,d), "")
            out_ws.cell(row=i, column=j).value = seat_code if seat_code else ""
    
    # Format header rows (bold, center, fill color)
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
    print("Global ILP roster generated successfully.")

if __name__ == "__main__":
    excel_filename = "TeamRoster.xlsx"  # Adjust path as needed
    generate_roster_schedule_ilp(excel_filename, designated_min=3, big_penalty=1000)