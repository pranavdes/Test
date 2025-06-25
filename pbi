
Q2: Create an M function that can handle incremental data loading with automatic schema drift detection and reconciliation.
Expected Answer:
mlet
    IncrementalLoadWithSchemaDrift = (
        SourceTable as table,
        LastRefreshDate as datetime,
        SchemaReferenceTable as table
    ) =>
    let
        // Get current schema
        CurrentSchema = Table.Schema(SourceTable),
        ReferenceSchema = Table.Schema(SchemaReferenceTable),
        
        // Detect schema changes
        CurrentColumns = CurrentSchema[Name],
        ReferenceColumns = ReferenceSchema[Name],
        
        NewColumns = List.Difference(CurrentColumns, ReferenceColumns),
        RemovedColumns = List.Difference(ReferenceColumns, CurrentColumns),
        
        // Handle schema drift
        SchemaAdjustedTable = 
            if List.Count(NewColumns) > 0 or List.Count(RemovedColumns) > 0
            then
                let
                    // Add missing columns with null values
                    AddColumns = List.Accumulate(
                        RemovedColumns,
                        SourceTable,
                        (state, current) => Table.AddColumn(state, current, each null)
                    ),
                    
                    // Remove extra columns or log them
                    FinalTable = Table.SelectColumns(AddColumns, ReferenceColumns)
                in
                    FinalTable
            else SourceTable,
        
        // Apply incremental filter
        FilteredTable = Table.SelectRows(
            SchemaAdjustedTable,
            each [ModifiedDate] > LastRefreshDate
        )
    in
        FilteredTable
in
    IncrementalLoadWithSchemaDrift







=========================================================================================
# M Function Explanation: Incremental Loading with Schema Drift Detection

## The Business Problem

### What is Incremental Data Loading?
Instead of reloading all data every time (full refresh), incremental loading only imports new or changed records since the last refresh. This is crucial for:
- **Performance**: Loading 1 million new records vs 100 million total records
- **Resource efficiency**: Less memory, CPU, and network usage
- **Faster refresh times**: Minutes instead of hours
- **Real-time analytics**: More frequent data updates

### What is Schema Drift?
Schema drift occurs when the source data structure changes over time:
- **New columns added**: "customer_loyalty_tier" field added to customer table
- **Columns removed**: "fax_number" field deprecated
- **Data type changes**: "phone_number" changes from text to numeric
- **Column order changes**: Fields rearranged in source system

**Real-world example**: Your sales system adds a new "discount_reason" column, but your Power BI model breaks because it doesn't expect this column.

## The M Function Solution

Let's break down the function step by step:

```m
let
    IncrementalLoadWithSchemaDrift = (
        SourceTable as table,
        LastRefreshDate as datetime,
        SchemaReferenceTable as table
    ) =>
```

### Function Parameters
- **SourceTable**: Current data from source system
- **LastRefreshDate**: When we last successfully loaded data
- **SchemaReferenceTable**: Our "expected" schema (what Power BI model expects)

## Step 1: Schema Detection and Comparison

```m
    let
        // Get current schema
        CurrentSchema = Table.Schema(SourceTable),
        ReferenceSchema = Table.Schema(SchemaReferenceTable),
        
        // Detect schema changes
        CurrentColumns = CurrentSchema[Name],
        ReferenceColumns = ReferenceSchema[Name],
        
        NewColumns = List.Difference(CurrentColumns, ReferenceColumns),
        RemovedColumns = List.Difference(ReferenceColumns, CurrentColumns),
```

### What's happening here:

**Table.Schema()** returns metadata about table structure:
```m
// Example of what Table.Schema returns:
[
    [Name="CustomerID", Kind="number", Type=Int64.Type],
    [Name="CustomerName", Kind="text", Type=Text.Type],
    [Name="SignupDate", Kind="datetime", Type=DateTime.Type]
]
```

**List.Difference()** finds columns that exist in one list but not the other:
```m
// If CurrentColumns = {"CustomerID", "CustomerName", "LoyaltyTier"}
// And ReferenceColumns = {"CustomerID", "CustomerName", "SignupDate"}
// Then:
NewColumns = {"LoyaltyTier"}        // New in source
RemovedColumns = {"SignupDate"}     // Missing from source
```

## Step 2: Schema Reconciliation

```m
        // Handle schema drift
        SchemaAdjustedTable = 
            if List.Count(NewColumns) > 0 or List.Count(RemovedColumns) > 0
            then
                let
                    // Add missing columns with null values
                    AddColumns = List.Accumulate(
                        RemovedColumns,
                        SourceTable,
                        (state, current) => Table.AddColumn(state, current, each null)
                    ),
                    
                    // Remove extra columns or log them
                    FinalTable = Table.SelectColumns(AddColumns, ReferenceColumns)
                in
                    FinalTable
            else SourceTable,
```

### Schema Reconciliation Logic:

**List.Accumulate()** is like a loop that processes each item in a list:
```m
// Example: Adding missing columns
// If RemovedColumns = {"SignupDate", "LastLoginDate"}
// This will:
// 1. Add "SignupDate" column with null values
// 2. Add "LastLoginDate" column with null values
```

**Table.SelectColumns()** keeps only the columns we want:
```m
// Removes any extra columns that appeared in source but aren't in our model
// Ensures consistent column order
```

### Real-world scenarios this handles:

1. **New column in source**: 
   - Source adds "customer_segment" 
   - Function ignores it (removes during SelectColumns)
   - Your Power BI model continues working

2. **Removed column in source**:
   - Source removes "fax_number"
   - Function adds it back with null values
   - Your existing DAX measures that reference "fax_number" don't break

## Step 3: Incremental Filtering

```m
        // Apply incremental filter
        FilteredTable = Table.SelectRows(
            SchemaAdjustedTable,
            each [ModifiedDate] > LastRefreshDate
        )
    in
        FilteredTable
```

### Incremental Logic:
- Only gets records modified after last successful refresh
- Assumes source has a "ModifiedDate" or similar timestamp column
- Dramatically reduces data volume

**Example**:
```m
// If LastRefreshDate = 2024-01-15 08:00:00
// Only gets records where ModifiedDate > 2024-01-15 08:00:00
// Instead of all 10 million records, maybe only 50,000 new/changed records
```

## Complete Function in Context

```m
let
    IncrementalLoadWithSchemaDrift = (
        SourceTable as table,
        LastRefreshDate as datetime,
        SchemaReferenceTable as table
    ) =>
    let
        // Schema detection
        CurrentSchema = Table.Schema(SourceTable),
        ReferenceSchema = Table.Schema(SchemaReferenceTable),
        CurrentColumns = CurrentSchema[Name],
        ReferenceColumns = ReferenceSchema[Name],
        NewColumns = List.Difference(CurrentColumns, ReferenceColumns),
        RemovedColumns = List.Difference(ReferenceColumns, CurrentColumns),
        
        // Schema reconciliation
        SchemaAdjustedTable = 
            if List.Count(NewColumns) > 0 or List.Count(RemovedColumns) > 0
            then
                let
                    AddColumns = List.Accumulate(
                        RemovedColumns,
                        SourceTable,
                        (state, current) => Table.AddColumn(state, current, each null)
                    ),
                    FinalTable = Table.SelectColumns(AddColumns, ReferenceColumns)
                in
                    FinalTable
            else SourceTable,
        
        // Incremental filtering
        FilteredTable = Table.SelectRows(
            SchemaAdjustedTable,
            each [ModifiedDate] > LastRefreshDate
        )
    in
        FilteredTable
in
    IncrementalLoadWithSchemaDrift
```

## How to Use This Function

### 1. Setup Reference Table
```m
// Create a reference table with your expected schema
ReferenceTable = #table(
    {"CustomerID", "CustomerName", "SignupDate", "LastPurchaseDate"},
    {{1, "John Doe", #datetime(2024,1,1,0,0,0), #datetime(2024,1,15,0,0,0)}}
)
```

### 2. Get Last Refresh Date
```m
// This could come from a parameter, file, or database
LastRefresh = #datetime(2024, 1, 15, 8, 0, 0)
```

### 3. Apply the Function
```m
// Your main query
Source = GetDataFromAPI(), // or database, file, etc.
CleanedData = IncrementalLoadWithSchemaDrift(Source, LastRefresh, ReferenceTable)
```

## Advanced Enhancements

### 1. Data Type Validation
```m
// Enhanced version with type checking
ValidateDataTypes = (table as table, referenceSchema as table) =>
    let
        CurrentSchema = Table.Schema(table),
        TypeMismatches = List.Select(
            CurrentSchema[Name],
            (columnName) =>
                let
                    CurrentType = List.First(
                        List.Select(CurrentSchema, each [Name] = columnName)
                    )[Type],
                    ReferenceType = List.First(
                        List.Select(Table.Schema(referenceSchema), each [Name] = columnName)
                    )[Type]
                in
                    CurrentType <> ReferenceType
        )
    in
        if List.Count(TypeMismatches) > 0
        then error "Data type mismatches found in columns: " & Text.Combine(TypeMismatches, ", ")
        else table
```

### 2. Logging Schema Changes
```m
// Log schema changes to a table for monitoring
LogSchemaChanges = (newColumns as list, removedColumns as list) =>
    let
        LogTable = #table(
            {"ChangeType", "ColumnName", "DetectedDate"},
            List.Combine({
                List.Transform(newColumns, each {"Added", _, DateTime.LocalNow()}),
                List.Transform(removedColumns, each {"Removed", _, DateTime.LocalNow()})
            })
        )
    in
        LogTable
```

## Performance Considerations

### 1. Query Folding
- Ensure the incremental filter can be "folded" to the source database
- Use simple comparison operators (`>`, `>=`, `=`)
- Avoid complex M functions in the filter condition

### 2. Memory Usage
- Process schema changes before applying incremental filter
- This ensures you're only working with the subset of data you need

### 3. Error Handling
```m
// Add try/otherwise for robust error handling
SafeSchemaAdjustment = 
    try SchemaAdjustedTable
    otherwise 
        let
            ErrorMessage = "Schema adjustment failed: " & [Error][Message],
            LogError = // Log to error table
        in
            error ErrorMessage
```

## Common Use Cases

### 1. API Data with Evolving Schema
```m
// Social media API that adds new engagement metrics
Source = GetFacebookData(),
ProcessedData = IncrementalLoadWithSchemaDrift(
    Source, 
    LastAPICallDate, 
    FacebookReferenceSchema
)
```

### 2. CSV Files with Changing Structure
```m
// Monthly sales files where format occasionally changes
Source = Csv.Document(FilePath),
ProcessedData = IncrementalLoadWithSchemaDrift(
    Source,
    LastFileProcessDate,
    SalesFileReferenceSchema
)
```

### 3. Database Views with Schema Evolution
```m
// Database view that gets new columns during application updates
Source = Sql.Database("server", "database", [Query="SELECT * FROM SalesView"]),
ProcessedData = IncrementalLoadWithSchemaDrift(
    Source,
    LastDBRefresh,
    SalesViewReferenceSchema
)
```

## Why This Approach is Expert-Level

### 1. **Handles Real-World Complexity**
- Production systems change frequently
- Manual schema updates are error-prone and time-consuming

### 2. **Performance Optimization**
- Combines incremental loading with schema management
- Prevents full reloads when only schema changes

### 3. **Robust Error Prevention**
- Prevents model breaks due to schema changes
- Maintains data consistency across refreshes

### 4. **Enterprise Scalability**
- Works with large datasets (millions of rows)
- Handles multiple data sources with different evolution patterns

This function demonstrates deep understanding of Power Query's functional programming paradigm, production data challenges, and performance optimization techniques that only come with extensive hands-on experience.
