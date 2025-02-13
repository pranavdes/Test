import calendar
import random
from datetime import datetime
import pandas as pd
from pulp import LpProblem, LpMaximize, LpVariable, lpSum, LpBinary, LpStatus
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

def get_named_cell_value(wb, cell_name):
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
    for tbl in ws._tables:
        if tbl.name == table_name:
            ref = tbl.ref
            cells = ws[ref]
            data = [[cell.value for cell in row] for row in cells]
            return pd.DataFrame(data[1:], columns=data[0])
    raise ValueError(f"Table '{table_name}' not found on worksheet '{ws.title}'.")

def get_working_dates(year, month, public_holidays):
    num_days = calendar.monthrange(year, month)[1]
    all_dates = [datetime(year, month, d) for d in range(1, num_days + 1)]
    holiday_dates = set(pd.to_datetime(h).date() for h in public_holidays)
    working = [dt for dt in all_dates if dt.weekday() < 5 and dt.date() not in holiday_dates]
    return working

def parse_days_string(days_str):
    """
    Splits something like 'Mon, Wed, Fri' or 'Monday, Tuesday' into a set of lowercase day abbreviations + full names.
    We'll store both for easy matching.
    """
    if not isinstance(days_str, str):
        return set()
    parts = [p.strip() for p in days_str.split(',')]
    day_set = set()
    for p in parts:
        p_l = p.lower()
        # If user typed "Mon" or "Monday", we store both forms
        # so we can match either day_abbr or day_full
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

def matches_special_subteam(day, df_special, working_dates, subteam_of_employee):
    """
    Returns True if 'day' is declared special for a sub-team that does NOT match subteam_of_employee.
    If so, we can't assign that employee. Otherwise, returns False.
    """
    # If day is special for sub-team X, employees not in X are excluded
    for _, row in df_special.iterrows():
        descriptor = str(row["DayDescriptor"]).strip()
        st = row["SubTeam"]
        if is_day_descriptor_match(day, descriptor, working_dates):
            # If the employee's sub-team != st, exclude them
            if subteam_of_employee != st:
                return True
    return False

def is_day_descriptor_match(date_obj, descriptor, working_dates):
    """
    Similar to 'matches_day_descriptor' from earlier examples.
    '1st Tue', 'Last Friday', etc.
    """
    desc = descriptor.strip().lower().split()
    if len(desc) < 2:
        return False
    # We won't re-implement the entire parse logic here for brevity
    # We'll do a simpler approach or re-use from earlier if needed
    # For clarity, let's do a small approach:
    from_dayname = date_obj.strftime("%a").lower()  # e.g. 'mon'
    from_dayfull = date_obj.strftime("%A").lower()  # e.g. 'monday'
    
    # find occurrence token
    occ = desc[0]  # '1st', 'last', etc.
    day_str = desc[-1]  # 'tue', 'tuesday', 'friday', etc.
    
    # Check day match
    if not (from_dayname.startswith(day_str) or from_dayfull == day_str):
        return False
    
    # Collect all working dates that share the same weekday
    needed_wd = date_obj.weekday()
    same_wd = [d for d in working_dates if d.month == date_obj.month and d.weekday() == needed_wd]
    same_wd.sort()
    
    if occ == 'last':
        return date_obj == same_wd[-1]
    else:
        # parse e.g. '1st', '2nd'
        digit_part = "".join(c for c in occ if c.isdigit())
        if not digit_part.isdigit():
            return False
        idx = int(digit_part) - 1
        if 0 <= idx < len(same_wd):
            return date_obj == same_wd[idx]
        else:
            return False

def generate_roster_schedule_ilp(excel_file):
    """
    Builds and solves an ILP to ensure every employee meets their required days
    if feasible, with seat preferences, sub-team designated days (priority),
    special sub-team days (exclusive), and fixed seats.
    
    Output is written in a column-oriented format: each date is a column,
    the second row is the weekday, then each row after that is a seat code
    with the occupant's name (or blank).
    """
    wb = load_workbook(excel_file)
    static_ws = wb["Static Data"]
    
    # Named cells
    office_percentage = get_named_cell_value(wb, "OfficePercentage")  # e.g. 0.6
    target_month_year = get_named_cell_value(wb, "TargetMonthYear")   # e.g. "Mar-25"
    
    month_str, year_str = target_month_year.split("-")
    month = datetime.strptime(month_str, "%b").month
    if len(year_str) == 2:
        year = int("20" + year_str)
    else:
        year = int(year_str)
    
    # Tables
    df_employees       = get_table_as_df(static_ws, "EmployeeData")
    df_seats           = get_table_as_df(static_ws, "SeatData")
    df_public_holidays = get_table_as_df(static_ws, "PublicHolidays")
    df_subteam_days    = get_table_as_df(static_ws, "SubTeamOfficeDays")
    df_special_days    = get_table_as_df(static_ws, "SpecialSubTeamDays")
    df_seat_pref       = get_table_as_df(static_ws, "SeatPreferences")
    
    # Build sets
    employees = df_employees["EmployeeID"].tolist()
    seats = df_seats["SeatCode"].tolist()
    
    # Working dates
    working_dates = get_working_dates(year, month, df_public_holidays["Date"])
    working_dates.sort()  # for consistent ordering
    
    # Each employee's required days
    total_wd = len(working_dates)
    required_days_val = round(total_wd * office_percentage)
    required_days = {emp: required_days_val for emp in employees}
    
    # Map sub-teams, employee names
    emp_subteam = dict(zip(df_employees["EmployeeID"], df_employees["SubTeam"]))
    emp_names   = dict(zip(df_employees["EmployeeID"], df_employees["EmployeeName"]))
    
    # For seat preferences, we'll define a small bonus
    seat_pref_bonus = {}
    for _, row in df_seat_pref.iterrows():
        e = row["EmployeeID"]
        s = row["SeatCode"]
        seat_pref_bonus[(e, s)] = 10  # an arbitrary positive bonus for pref
    
    # For sub-team designated days, a smaller bonus
    # We'll store which sub-teams are designated for each weekday
    # e.g. "Team A" => "Mon, Wed"
    subteam_days_map = {}
    # subteam_days_map[subteam_name] = set of day abbreviations
    for _, row in df_subteam_days.iterrows():
        st = row["SubTeam"]
        ds = parse_days_string(row["OfficeDays"])
        subteam_days_map.setdefault(st, set()).update(ds)
    
    # We'll define a sub-team day bonus of 5 if an employee is on a day that matches their sub-team
    subteam_bonus = 5
    fill_bonus = 1  # reward simply occupying a seat
    
    # For seat day constraints
    seat_day_avail = {}  # seat_day_avail[s, d] = True if seat s is allowed on day d
    for _, srow in df_seats.iterrows():
        s_code = srow["SeatCode"]
        seat_days_set = parse_days_string(srow["Days"])
        # For each working day, check if day is in seat_days_set
        for d in working_dates:
            d_abbr = d.strftime("%a").lower()  # mon
            d_full = d.strftime("%A").lower()  # monday
            # If seat_days_set is empty or doesn't contain d_abbr/d_full, seat not available
            if d_abbr in seat_days_set or d_full in seat_days_set:
                seat_day_avail[(s_code, d)] = True
            else:
                seat_day_avail[(s_code, d)] = False
    
    # For fixed seats
    # If seat is fixed to emp on certain days, we must force x[e,s,d] = 1 and others=0
    # We'll store a dictionary: fixed_assign[s, d] = e or None
    fixed_assign = {}
    for _, row in df_seats.iterrows():
        if str(row["SeatType"]).strip().lower() == "fixed":
            assigned_emp = row.get("AssignedEmployeeID")
            if pd.notna(assigned_emp):
                s_code = row["SeatCode"]
                seat_days_set = parse_days_string(row["Days"])
                for d in working_dates:
                    d_abbr = d.strftime("%a").lower()
                    d_full = d.strftime("%A").lower()
                    if d_abbr in seat_days_set or d_full in seat_days_set:
                        fixed_assign[(s_code, d)] = assigned_emp
    
    # Build the ILP
    model = LpProblem("GlobalRostering", LpMaximize)
    
    # Decision vars: x[e,s,d] in {0,1}
    x = {}
    for e in employees:
        for s in seats:
            for d in working_dates:
                var_name = f"x_{e}_{s}_{d.strftime('%d')}"
                x[(e,s,d)] = LpVariable(var_name, cat=LpBinary)
    
    # 1) Each seat can have at most 1 occupant per day
    for s in seats:
        for d in working_dates:
            model += lpSum(x[(e,s,d)] for e in employees) <= 1, f"SeatOccupancy_{s}_{d}"
    
    # 2) Each employee can only occupy at most 1 seat per day
    for e in employees:
        for d in working_dates:
            model += lpSum(x[(e,s,d2)] for s in seats for d2 in [d]) <= 1, f"EmployeeOneSeat_{e}_{d}"
    
    # 3) Each employee must meet required days
    for e in employees:
        model += lpSum(x[(e,s,d)] for s in seats for d in working_dates) >= required_days[e], f"RequiredDays_{e}"
    
    # 4) If seat is fixed for day => x[fixedEmp, seat, day] = 1, others=0
    # We'll do it by forcing constraints
    for (s_code, d), e_fix in fixed_assign.items():
        # x[e_fix,s_code,d] = 1
        model += x[(e_fix, s_code, d)] == 1, f"FixedSeat_{s_code}_{d}"
        # For all other employees e != e_fix => x[e, s_code, d] = 0
        for e2 in employees:
            if e2 != e_fix:
                model += x[(e2, s_code, d)] == 0, f"FixedSeatZero_{s_code}_{d}_{e2}"
    
    # 5) If day is special for sub-team T => employees not in T can't come
    # We'll do that day-by-day after we solve the "which days are special for which sub-team"
    # Actually we can incorporate it in constraints: for each day, check if it's special sub-team
    # But we can have multiple special day definitions. If we find a match, that day is exclusive
    # We'll do the same approach: if day matches descriptor for sub-team T, then for employees e
    # who are not in T => x[e,s,d]=0
    for d in working_dates:
        # figure out if there's a special sub-team for d
        sub_teams_for_this_day = []
        for _, row2 in df_special_days.iterrows():
            if is_day_descriptor_match(d, row2["DayDescriptor"], working_dates):
                sub_teams_for_this_day.append(row2["SubTeam"])
        # If multiple lines match, we combine them? Or assume only one sub-team per day?
        # We'll assume only one special sub-team can match a day (or the last one in the table).
        if sub_teams_for_this_day:
            special_t = sub_teams_for_this_day[-1]  # pick the first or last
            # Exclude employees not in special_t
            for e in employees:
                if emp_subteam[e] != special_t:
                    for s in seats:
                        model += x[(e,s,d)] == 0, f"SpecialExcl_{e}_{s}_{d}"
    
    # 6) If seat_day_avail[s,d] = False => x[e,s,d] = 0 for all e
    for s in seats:
        for d in working_dates:
            if not seat_day_avail[(s,d)]:
                for e in employees:
                    model += x[(e,s,d)] == 0, f"SeatNotAvail_{s}_{d}_{e}"
    
    # Build the objective: seat preferences, sub-team designated day bonus, plus fill
    # seat_pref_bonus[(e,s)] = e.g. 10 if e prefers s, else 0
    # sub-team day => if day_abbr is designated for sub-team of e => +5
    # fill => +1 for every seat assignment
    # We do a sum of (pref + subteam bonus + fill) * x[e,s,d]
    objective_terms = []
    
    # Pre-calculate sub-team day sets for quick lookup
    # subteam_days_map[st] => set of day tokens
    for e in employees:
        e_st = emp_subteam[e]
        for s in seats:
            pref_b = seat_pref_bonus.get((e,s), 0)
            for d in working_dates:
                fill_b = 1  # reward any assignment
                # sub-team day bonus?
                day_abbr = d.strftime("%a").lower()
                day_full = d.strftime("%A").lower()
                st_day_bonus = 0
                if e_st in subteam_days_map:
                    st_set = subteam_days_map[e_st]
                    if (day_abbr in st_set) or (day_full in st_set):
                        st_day_bonus = 5
                total_bonus = pref_b + st_day_bonus + fill_b
                objective_terms.append(total_bonus * x[(e,s,d)])
    
    model += lpSum(objective_terms), "MaximizePreferencesAndUsage"
    
    # Solve
    model.solve()
    
    if LpStatus[model.status] != "Optimal":
        print("No feasible solution found or solver did not find an optimal solution.")
        return
    
    # Extract solution
    # For each day, seat => assigned employee (or None)
    day_seat_assignment = { (d,s): None for d in working_dates for s in seats }
    
    for e in employees:
        for s in seats:
            for d in working_dates:
                if x[(e,s,d)].varValue == 1:
                    day_seat_assignment[(d,s)] = e
    
    # --- OUTPUT SHEET in column-oriented format ---
    out_sheet_name = target_month_year
    if out_sheet_name in wb.sheetnames:
        out_ws = wb[out_sheet_name]
        # Clear
        for row in out_ws.iter_rows(min_row=1, max_row=out_ws.max_row,
                                    min_col=1, max_col=out_ws.max_column):
            for cell in row:
                cell.value = None
    else:
        out_ws = wb.create_sheet(title=out_sheet_name)
    
    # We want:
    # Row1: each day col => "YYYY-MM-DD"
    # Row2: each day col => "Mon"
    # Then for each seat => occupant's name
    # So the first column can be "SeatCode" as the header
    # We'll do 1-based indexing in openpyxl. So col=2.. for each date
    # row=3.. for each seat
    out_ws.cell(row=1, column=1).value = "Seat / Date"
    out_ws.cell(row=2, column=1).value = "Day"
    
    # Write date headers
    for idx, d in enumerate(working_dates):
        col = idx + 2
        out_ws.cell(row=1, column=col).value = d.strftime("%Y-%m-%d")
        out_ws.cell(row=2, column=col).value = d.strftime("%a")
    
    # Now each seat is a row
    # row=3..  so seat i => row= i+2
    for i, s_code in enumerate(seats):
        row_i = i + 3
        out_ws.cell(row=row_i, column=1).value = s_code
        # fill occupant
        for idx, d in enumerate(working_dates):
            col = idx + 2
            occupant_emp = day_seat_assignment[(d,s_code)]
            if occupant_emp:
                occupant_name = emp_names[occupant_emp]
                out_ws.cell(row=row_i, column=col).value = occupant_name
            else:
                out_ws.cell(row=row_i, column=col).value = ""
    
    # Some formatting
    header_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
    # First row
    for cell in out_ws[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    # Second row
    for cell in out_ws[2]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    # First column
    for row in out_ws.iter_rows(min_row=1, max_row=2+len(seats), min_col=1, max_col=1):
        for cell in row:
            cell.font = Font(bold=True)
    
    # Optionally auto-width
    for col_obj in out_ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_obj[0].column)
        for c in col_obj:
            if c.value and isinstance(c.value, str):
                max_len = max(max_len, len(c.value))
        out_ws.column_dimensions[col_letter].width = max_len + 2
    
    wb.save(excel_file)
    print("Global ILP schedule generated successfully.")

if __name__ == "__main__":
    excel_filename = "TeamRoster.xlsx"
    generate_roster_schedule_ilp(excel_filename)