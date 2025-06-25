Customer_Sales_Matrix Table:
CustomerID | Jan_Electronics | Jan_Clothing | Feb_Electronics | Feb_Clothing | Mar_Electronics | Mar_Clothing
1001 | 100 | 50 | 150 | 75 | 200 | 80
1002 | 200 | 0 | 0 | 100 | 250 | 120


Dynamically unpivot ALL month-category combinations (regardless of how many months/categories are added)


CustomerID	Month	Category	Value	Sales_Trend
1001	Jan	Electronics	$100.00	null
1001	Feb	Electronics	$150.00	50.00%
1001	Mar	Electronics	$200.00	33.33%




Step 1: Initial Data Source
mSource = Customer_Sales_Matrix,
Purpose: Load the source table with customer sales data across different month-category combinations.

Step 2: Dynamic Unpivoting
m#"Unpivoted Columns" = Table.UnpivotOtherColumns(Source, {"CustomerID"}, "Attribute", "Value"),
Purpose:

Unpivot all columns except CustomerID
Creates two new columns: "Attribute" (column names) and "Value" (cell values)
Makes the wide table format into a long format

Before:
CustomerIDJan_ElectronicsJan_ClothingFeb_Electronics100110050150
After:
CustomerIDAttributeValue1001Jan_Electronics1001001Jan_Clothing501001Feb_Electronics150

Step 3: Create Enhanced Parsing Function
mParseAttributeAdvanced = (attributeName as text) as record =>
let
    Parts = Text.Split(attributeName, "_"),
    IsValidFormat = List.Count(Parts) = 2,
    Month = if IsValidFormat then Parts{0} else "Unknown",
    Category = if IsValidFormat then Parts{1} else "Unknown",
    
    // Validate month names
    ValidMonths = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"},
    IsValidMonth = List.Contains(ValidMonths, Month),
    
    FinalMonth = if IsValidMonth then Month else "Invalid",
    FinalCategory = if IsValidFormat then Category else "Invalid"
in
    [Month = FinalMonth, Category = FinalCategory, IsValid = IsValidFormat and IsValidMonth],
Purpose:

Create a custom function that validates and parses attribute names
Splits "Jan_Electronics" into Month="Jan" and Category="Electronics"
Validates that the format is correct (has exactly 2 parts separated by "_")
Validates that the month is a valid 3-letter month abbreviation
Returns a record with parsed values and validation flag


Step 4: Apply Enhanced Parsing Function
m#"Added Parsed Data" = Table.AddColumn(#"Unpivoted Columns", "ParsedData", 
    each ParseAttributeAdvanced([Attribute])),
Purpose:

Add a new column called "ParsedData"
Apply the custom parsing function to each row's Attribute value
Creates a record column containing the parsed month, category, and validation status


Step 5: Expand the Record Column
m#"Expanded ParsedData" = Table.ExpandRecordColumn(#"Added Parsed Data", "ParsedData", 
    {"Month", "Category", "IsValid"}, {"Month", "Category", "IsValid"}),
Purpose:

Convert the record column into separate columns
Extract Month, Category, and IsValid fields into individual columns
Remove the original ParsedData record column

Result:
CustomerIDAttributeValueMonthCategoryIsValid1001Jan_Electronics100JanElectronicsTRUE

Step 6: Filter Valid Data Only
m#"Filtered Valid Data" = Table.SelectRows(#"Expanded ParsedData", each [IsValid] = true),
Purpose:

Remove any rows where the parsing failed (IsValid = false)
Ensures we only work with properly formatted month-category combinations
Provides data quality assurance


Step 7: Clean Up Unnecessary Columns
m#"Removed Columns" = Table.RemoveColumns(#"Filtered Valid Data", {"Attribute", "IsValid"}),
Purpose:

Remove the original "Attribute" column (no longer needed since we have Month and Category)
Remove the "IsValid" column (used only for filtering)
Keep only relevant columns for further processing


Step 8: Create Enhanced Month Details Function
mMonthDetails = (monthText as text) as record =>
let
    MonthMap = [
        Jan = [Number = 1, Quarter = 1], Feb = [Number = 2, Quarter = 1], Mar = [Number = 3, Quarter = 1],
        Apr = [Number = 4, Quarter = 2], May = [Number = 5, Quarter = 2], Jun = [Number = 6, Quarter = 2],
        Jul = [Number = 7, Quarter = 3], Aug = [Number = 8, Quarter = 3], Sep = [Number = 9, Quarter = 3],
        Oct = [Number = 10, Quarter = 4], Nov = [Number = 11, Quarter = 4], Dec = [Number = 12, Quarter = 4]
    ],
    Details = Record.Field(MonthMap, monthText)
in
    Details,
Purpose:

Create a function that converts month abbreviations to numbers and quarters
Returns both month number (for sorting) and quarter (for seasonality analysis)
Uses a record-based lookup for efficient conversion


Step 9: Apply Month Details Function
m#"Added Month Details" = Table.AddColumn(#"Removed Columns", "MonthDetails", 
    each MonthDetails([Month])),
Purpose:

Add month number and quarter information to each row
Creates a record column with month number and quarter


Step 10: Expand Month Details
m#"Expanded Month Details" = Table.ExpandRecordColumn(#"Added Month Details", "MonthDetails", 
    {"Number", "Quarter"}, {"MonthNumber", "Quarter"}),
Purpose:

Extract month number and quarter into separate columns
These will be used for sorting and seasonality calculations


Step 11: Sort Data for Trend Calculations
m#"Sorted Data" = Table.Sort(#"Expanded Month Details", {
    {"CustomerID", Order.Ascending}, 
    {"Category", Order.Ascending}, 
    {"MonthNumber", Order.Ascending}
}),
Purpose:

Sort data to ensure proper order for month-over-month calculations
Primary sort: CustomerID (group by customer)
Secondary sort: Category (group by category within customer)
Tertiary sort: MonthNumber (chronological order within customer-category groups)


Step 12: Calculate Advanced Trend Metrics
m#"Added Trend Metrics" = Table.AddColumn(#"Sorted Data", "TrendMetrics", 
    each 
    let
        CurrentCustomer = [CustomerID],
        CurrentCategory = [Category],
        CurrentMonth = [MonthNumber],
        CurrentValue = [Value],
        
        // Get all data for current customer and category
        CustomerCategoryData = Table.SelectRows(#"Sorted Data", each 
            [CustomerID] = CurrentCustomer and [Category] = CurrentCategory),
        
        // Sort by month
        SortedData = Table.Sort(CustomerCategoryData, {{"MonthNumber", Order.Ascending}}),
        
        // Find current row position
        CurrentRowIndex = List.PositionOf(Table.Column(SortedData, "MonthNumber"), CurrentMonth),
        
        // Previous month calculations
        PreviousValue = if CurrentRowIndex = 0 or CurrentRowIndex = -1 then null
                       else Table.Column(SortedData, "Value"){CurrentRowIndex - 1},
        
        MoMGrowth = if PreviousValue = null or PreviousValue = 0 then null
                   else (CurrentValue - PreviousValue) / PreviousValue,
        
        // Calculate average for the customer-category combination
        AllValues = Table.Column(SortedData, "Value"),
        AverageValue = List.Average(AllValues),
        
        // Performance vs average
        VsAverage = if AverageValue = 0 then null else (CurrentValue - AverageValue) / AverageValue
    in
        [
            MoM_Growth = MoMGrowth,
            Vs_Average = VsAverage,
            Is_Above_Average = CurrentValue > AverageValue
        ]
),
Purpose:

Calculate month-over-month growth for each customer-category combination
Get all data for the current customer-category to find previous month's value
Calculate performance vs. average for the customer-category combination
Return multiple metrics in a record format

Key Logic:

Filter data for current customer and category
Find the current month's position in the chronological sequence
Get previous month's value for growth calculation
Calculate average performance for comparison metrics


Step 13: Expand Trend Metrics
m#"Expanded Trend Metrics" = Table.ExpandRecordColumn(#"Added Trend Metrics", "TrendMetrics", 
    {"MoM_Growth", "Vs_Average", "Is_Above_Average"}, 
    {"Sales_Trend", "Vs_Category_Average", "Above_Average"}),
Purpose:

Extract the calculated metrics into separate columns
Rename columns for clarity (MoM_Growth becomes Sales_Trend)
Provide multiple performance indicators


Step 14: Create Enhanced Seasonality Analysis
m#"Added Enhanced Seasonality" = Table.AddColumn(#"Expanded Trend Metrics", "Seasonality_Details", 
    each 
    let
        Q = [Quarter],
        Month = [MonthNumber],
        SeasonFlag = if Q = 4 then "High Season"
                    else if Q = 1 then "Post-Holiday"
                    else if List.Contains({5, 6, 7, 8}, Month) then "Summer"
                    else "Regular Season",
        
        IsHolidayQuarter = Q = 4,
        IsSummerSeason = List.Contains({6, 7, 8}, Month)
    in
        [
            Seasonality_Flag = SeasonFlag,
            Is_Holiday_Quarter = IsHolidayQuarter,
            Is_Summer_Season = IsSummerSeason
        ]
),
Purpose:

Create detailed seasonality analysis beyond simple Q4 flagging
Identify different seasonal patterns:

Q4: High Season (Oct, Nov, Dec)
Q1: Post-Holiday (Jan, Feb, Mar)
Summer months: Special summer season
Other months: Regular Season


Provide boolean flags for specific seasonal analysis


Step 15: Expand Seasonality Details
m#"Expanded Seasonality" = Table.ExpandRecordColumn(#"Added Enhanced Seasonality", "Seasonality_Details", 
    {"Seasonality_Flag", "Is_Holiday_Quarter", "Is_Summer_Season"}, 
    {"Seasonality_Flag", "Is_Holiday_Quarter", "Is_Summer_Season"}),
Purpose:

Convert seasonality record into separate columns
Provide multiple seasonality indicators for different analysis needs


Step 16: Remove Helper Columns
m#"Removed Helper Columns" = Table.RemoveColumns(#"Expanded Seasonality", {"MonthNumber", "Quarter"}),
Purpose:

Clean up intermediate columns used for calculations
Keep only the final analysis columns needed for reporting


Step 17: Set Final Data Types
m#"Final Types" = Table.TransformColumnTypes(#"Removed Helper Columns", {
    {"CustomerID", Int64.Type},
    {"Value", Currency.Type},
    {"Sales_Trend", Percentage.Type},
    {"Vs_Category_Average", Percentage.Type},
    {"Above_Average", type logical},
    {"Is_Holiday_Quarter", type logical},
    {"Is_Summer_Season", type logical}
}),
