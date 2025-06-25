# Customer Database Schema Evolution - Concrete M Function Example

## Business Context: Online Retail Company "ShopEasy"

### Database Tables:
- **`Customers`** - Main customer information
- **`CustomerAddresses`** - Customer shipping/billing addresses  
- **`CustomerOrders`** - Order history
- **`CustomerContacts`** - Phone numbers, social media contacts

## Customers Table Evolution Timeline

### January 2024: Initial Schema
```sql
-- Original Customers table structure
CREATE TABLE Customers (
    CustomerID INT PRIMARY KEY,
    FirstName VARCHAR(50),
    LastName VARCHAR(50), 
    Email VARCHAR(100),
    PhoneNumber VARCHAR(20),
    DateRegistered DATETIME,
    LastModifiedDate DATETIME
);
```

### March 2024: Loyalty Program Added
```sql
-- After loyalty program launch
ALTER TABLE Customers ADD LoyaltyTierID INT;
ALTER TABLE Customers ADD LoyaltyPoints INT DEFAULT 0;
ALTER TABLE Customers ADD LoyaltyJoinDate DATETIME;
```

### May 2024: GDPR Compliance
```sql
-- GDPR fields added, phone moved to separate table
ALTER TABLE Customers ADD GDPRConsentStatus VARCHAR(20) DEFAULT 'Pending';
ALTER TABLE Customers ADD ConsentDate DATETIME;
ALTER TABLE Customers DROP COLUMN PhoneNumber; -- Moved to CustomerContacts
```

### July 2024: Customer Segmentation
```sql
-- Marketing segmentation fields
ALTER TABLE Customers ADD CustomerSegment VARCHAR(30) DEFAULT 'Standard';
ALTER TABLE Customers ADD PreferredContactMethod VARCHAR(20) DEFAULT 'Email';
ALTER TABLE Customers ADD MarketingOptIn BIT DEFAULT 0;
```

## M Function Implementation with Real Table Names

```m
let
    // Function to handle Customers table incremental loading with schema drift
    LoadCustomersTableIncremental = (
        SourceCustomersTable as table,
        LastRefreshDateTime as datetime,
        CustomersReferenceTable as table
    ) =>
    let
        // Step 1: Compare current Customers table with reference schema
        CurrentSchema = Table.Schema(SourceCustomersTable),
        ReferenceSchema = Table.Schema(CustomersReferenceTable),
        
        CurrentColumns = CurrentSchema[Name],
        ReferenceColumns = ReferenceSchema[Name],
        
        // Find what's new or missing in Customers table
        NewColumnsInSource = List.Difference(CurrentColumns, ReferenceColumns),
        MissingColumnsInSource = List.Difference(ReferenceColumns, CurrentColumns),
        
        // Step 2: Handle Customers table schema changes
        CustomersSchemaFixed = 
            if List.Count(NewColumnsInSource) > 0 or List.Count(MissingColumnsInSource) > 0
            then
                let
                    // Add missing columns to Customers table with business defaults
                    AddMissingColumns = List.Accumulate(
                        MissingColumnsInSource,
                        SourceCustomersTable,
                        (currentTable, missingColumn) => 
                            // Add column with appropriate default based on Customers table business rules
                            if missingColumn = "LoyaltyTierID" then
                                Table.AddColumn(currentTable, missingColumn, each 1, type number) // Bronze = 1
                            else if missingColumn = "LoyaltyPoints" then
                                Table.AddColumn(currentTable, missingColumn, each 0, type number)
                            else if missingColumn = "GDPRConsentStatus" then
                                Table.AddColumn(currentTable, missingColumn, each "Pending", type text)
                            else if missingColumn = "CustomerSegment" then
                                Table.AddColumn(currentTable, missingColumn, each "Standard", type text)
                            else if missingColumn = "PreferredContactMethod" then
                                Table.AddColumn(currentTable, missingColumn, each "Email", type text)
                            else if missingColumn = "MarketingOptIn" then
                                Table.AddColumn(currentTable, missingColumn, each false, type logical)
                            else if Text.Contains(missingColumn, "Date") then
                                Table.AddColumn(currentTable, missingColumn, each null, type datetime)
                            else
                                Table.AddColumn(currentTable, missingColumn, each null, type text)
                    ),
                    
                    // Remove extra columns not in reference (keeps model stable)
                    MatchReferenceSchema = Table.SelectColumns(AddMissingColumns, ReferenceColumns)
                in
                    MatchReferenceSchema
            else SourceCustomersTable,
        
        // Step 3: Apply incremental filter to Customers table
        IncrementalCustomers = Table.SelectRows(
            CustomersSchemaFixed,
            each [LastModifiedDate] > LastRefreshDateTime
        ),
        
        // Step 4: Validate Customers table data quality
        ValidCustomers = Table.SelectRows(
            IncrementalCustomers,
            each 
                [CustomerID] <> null and 
                [FirstName] <> null and
                [LastName] <> null and
                [Email] <> null and
                Text.Contains([Email], "@") and
                [DateRegistered] <> null and
                [LastModifiedDate] <> null
        )
    in
        ValidCustomers
in
    LoadCustomersTableIncremental
```

## Setting Up Reference Schemas for Each Table

### Customers Table Reference Schema
```m
// This represents what your Power BI model expects from Customers table
CustomersReference = #table(
    {
        "CustomerID", 
        "FirstName", 
        "LastName", 
        "Email", 
        "LoyaltyTierID", 
        "LoyaltyPoints", 
        "GDPRConsentStatus", 
        "CustomerSegment", 
        "PreferredContactMethod", 
        "DateRegistered", 
        "LastModifiedDate"
    },
    {
        {1, "John", "Doe", "john@email.com", 1, 250, "Granted", "Premium", "Email", #datetime(2024,1,15,0,0,0), #datetime(2024,7,20,0,0,0)}
    }
)
```

### CustomerAddresses Table Reference Schema
```m
CustomerAddressesReference = #table(
    {
        "AddressID",
        "CustomerID", 
        "AddressType", 
        "StreetAddress", 
        "City", 
        "StateProvince", 
        "PostalCode", 
        "Country",
        "IsDefault",
        "LastModifiedDate"
    },
    {
        {1, 1, "Shipping", "123 Main St", "Springfield", "IL", "62701", "USA", true, #datetime(2024,1,15,0,0,0)}
    }
)
```

### CustomerOrders Table Reference Schema
```m
CustomerOrdersReference = #table(
    {
        "OrderID",
        "CustomerID",
        "OrderDate",
        "OrderTotal",
        "OrderStatus",
        "ShippingAddressID",
        "PaymentMethod",
        "LastModifiedDate"
    },
    {
        {1001, 1, #datetime(2024,7,15,0,0,0), 156.99, "Completed", 1, "Credit Card", #datetime(2024,7,16,0,0,0)}
    }
)
```

## Real Usage Example in Power BI

### Step 1: Set Parameters
```m
// Get last refresh time (from parameter table or file)
LastRefreshTime = #datetime(2024, 7, 19, 23, 59, 59)
```

### Step 2: Load Customers Table with Schema Drift Handling
```m
// Connect to your Customers table
CustomersSource = Sql.Database("ShopEasyDB", "Production", 
    [Query = "SELECT * FROM Customers WHERE IsActive = 1"]
),

// Apply incremental loading with schema drift protection
ProcessedCustomers = LoadCustomersTableIncremental(
    CustomersSource,
    LastRefreshTime,
    CustomersReference
)
```

### Step 3: Handle Related Tables
```m
// CustomerAddresses table with same protection
CustomerAddressesSource = Sql.Database("ShopEasyDB", "Production", 
    [Query = "SELECT * FROM CustomerAddresses"]
),

ProcessedAddresses = LoadCustomersTableIncremental(
    CustomerAddressesSource,
    LastRefreshTime, 
    CustomerAddressesReference
),

// CustomerOrders table (incremental loading)
CustomerOrdersSource = Sql.Database("ShopEasyDB", "Production", 
    [Query = "SELECT * FROM CustomerOrders"]
),

ProcessedOrders = LoadCustomersTableIncremental(
    CustomerOrdersSource,
    LastRefreshTime,
    CustomerOrdersReference
)
```

## Real Scenario: What Happens During Schema Changes

### Scenario 1: IT Adds New Column to Customers Table
**Date**: March 15, 2024  
**Change**: IT adds `LoyaltyTierID` and `LoyaltyPoints` to Customers table

**Without Schema Drift Protection:**
```
❌ Power BI refresh fails
❌ Error: "Column 'LoyaltyTierID' not found in destination"
❌ All customer reports break
❌ Emergency meeting with IT team
```

**With Schema Drift Protection:**
```
✅ Function detects new columns in Customers table
✅ Ignores new columns (removes them during SelectColumns)
✅ Existing customer reports continue working
✅ BI team updates model when ready
```

### Scenario 2: Your Team Updates Model Before IT
**Date**: May 1, 2024  
**Change**: You add GDPR fields to CustomersReference, but IT hasn't updated Customers table yet

**Without Schema Drift Protection:**
```
❌ Power BI shows null values for GDPR columns
❌ DAX measures that reference consent status break
❌ Compliance reports show incorrect data
```

**With Schema Drift Protection:**
```
✅ Function detects missing GDPR columns in source Customers table
✅ Adds GDPRConsentStatus = "Pending" to all records
✅ Adds ConsentDate = null until IT updates source
✅ Compliance reports work with default values
✅ Smooth transition when IT updates Customers table
```

### Scenario 3: IT Removes Column from Customers Table
**Date**: May 15, 2024  
**Change**: IT removes `PhoneNumber` from Customers table (moved to CustomerContacts)

**Your Power BI Model Still Expects PhoneNumber:**
```
✅ Function detects missing PhoneNumber column
✅ Adds PhoneNumber = null to all Customers records
✅ Existing customer reports don't break
✅ You can update model to join CustomerContacts table later
```

## Performance Impact with Real Numbers

### ShopEasy Customer Database:
- **Customers table**: 2.5 million records
- **Daily new customers**: 1,500
- **Daily customer updates**: 8,500 (profile changes, loyalty points, etc.)
- **Total daily changes**: 10,000 records

### Without Incremental Loading:
- Load all 2.5 million Customers records daily
- Process time: 45 minutes
- Memory usage: 850 MB
- Database load: High (full table scan)

### With Incremental Loading:
- Load only 10,000 changed Customers records
- Process time: 2 minutes
- Memory usage: 3.4 MB
- Database load: Minimal (index scan on LastModifiedDate)

## Interview Question Follow-ups

**Q**: "What if the Customers table doesn't have a LastModifiedDate column?"  
**A**: Use alternative strategies like CDC (Change Data Capture), triggers, or timestamp-based partitioning.

**Q**: "How would you handle data type changes in the Customers table?"  
**A**: Extend the function to compare data types and add conversion logic.

**Q**: "What about handling deletes in the Customers table?"  
**A**: Implement soft deletes with IsDeleted flag or use separate deletion tracking table.

This concrete example with real table names (Customers, CustomerAddresses, CustomerOrders) makes it easy for candidates to understand the business context and relate to their own experience with customer data systems.
