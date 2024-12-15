/**
 * Confluence Table Formatter Module
 * Version: 1.0.0
 * Purpose: Format dates and reviewer information in Confluence tables
 * 
 * Commit Message: Initial implementation of robust table formatter with error handling
 * Changes:
 * - Implemented robust date parsing and formatting
 * - Added comprehensive error handling
 * - Added detailed logging system
 * - Implemented table element validation
 * - Added retry mechanism for table formatting
 */

AJS.toInit(function($) {
    // Enable debug mode for development
    const DEBUG = true;

    // Configuration object for easy maintenance
    const CONFIG = {
        tableId: "Ownership\\&Scope",
        dateFields: ["SOP Next Review Date", "Last Review Date"],
        maxRetries: 3,
        retryDelay: 1000, // milliseconds
        validDatePatterns: [
            /^\d{4}-\d{2}-\d{2}$/, // yyyy-mm-dd
            /^\d{2}-\d{2}-\d{4}$/, // dd-mm-yyyy
            /^\d{2}\/\d{2}\/\d{4}$/, // dd/mm/yyyy
            /^\d{4}\/\d{2}\/\d{2}$/, // yyyy/mm/dd
        ]
    };

    /**
     * Logging utility for debugging
     */
    const Logger = {
        log: function(message, data = null) {
            if (DEBUG) {
                const timestamp = new Date().toISOString();
                const logMessage = `[${timestamp}] ${message}`;
                data ? console.log(logMessage, data) : console.log(logMessage);
            }
        },
        error: function(message, error = null) {
            const timestamp = new Date().toISOString();
            const errorMessage = `[${timestamp}] ERROR: ${message}`;
            error ? console.error(errorMessage, error) : console.error(errorMessage);
        }
    };

    /**
     * Validates and normalizes date strings
     * @param {string} dateString - The date string to validate
     * @returns {Object} - Object containing validation result and normalized date
     */
    function validateDateString(dateString) {
        if (!dateString || typeof dateString !== 'string') {
            return { isValid: false, normalizedDate: null };
        }

        const trimmedDate = dateString.trim();
        if (!trimmedDate || trimmedDate === '1970-01-01') {
            return { isValid: false, normalizedDate: null };
        }

        // Check against valid date patterns
        const isValidPattern = CONFIG.validDatePatterns.some(pattern => 
            pattern.test(trimmedDate)
        );

        if (!isValidPattern) {
            return { isValid: false, normalizedDate: null };
        }

        // Try to parse the date
        const parsedDate = new Date(trimmedDate);
        if (isNaN(parsedDate.getTime())) {
            return { isValid: false, normalizedDate: null };
        }

        return { 
            isValid: true, 
            normalizedDate: parsedDate 
        };
    }

    /**
     * Converts date format to a standardized string
     * @param {string} dateString - The date string to convert
     * @returns {string} - Formatted date string or empty string if invalid
     */
    function convertDateFormat(dateString) {
        try {
            const { isValid, normalizedDate } = validateDateString(dateString);
            
            if (!isValid) {
                Logger.log(`Invalid date string received: ${dateString}`);
                return '';
            }

            const options = { 
                year: 'numeric', 
                month: 'short', 
                day: '2-digit',
                timeZone: 'UTC' // Ensure consistent timezone handling
            };

            return normalizedDate
                .toLocaleDateString('en-US', options)
                .replace(/,/g, '')
                .replace(/(\w+) (\d+) (\d+)/, '$1 $2, $3');

        } catch (error) {
            Logger.error('Error in convertDateFormat:', error);
            return dateString; // Return original string if conversion fails
        }
    }

    /**
     * Validates table elements before processing
     * @param {jQuery} table - jQuery table element
     * @returns {boolean} - Whether the table is valid
     */
    function validateTable(table) {
        if (!table || !table.length) {
            Logger.error('Table not found');
            return false;
        }

        const hasRequiredStructure = CONFIG.dateFields.every(fieldName => {
            const headerExists = table.find(`th span:contains("${fieldName}")`).length > 0;
            if (!headerExists) {
                Logger.error(`Required field "${fieldName}" not found in table`);
            }
            return headerExists;
        });

        return hasRequiredStructure;
    }

    /**
     * Formats a single date field in the table
     * @param {jQuery} table - jQuery table element
     * @param {string} fieldName - Name of the date field
     * @returns {boolean} - Whether the formatting was successful
     */
    function formatDateField(table, fieldName) {
        try {
            const dateRow = table.find(`th span:contains("${fieldName}")`).closest('tr');
            if (!dateRow.length) {
                Logger.error(`Row not found for field: ${fieldName}`);
                return false;
            }

            const dateCell = dateRow.find('td span span');
            const dateCellContent = fieldName === "SOP Next Review Date" ? 
                dateCell.find('span') : dateCell;

            const originalDate = dateCellContent.text().trim();
            const newDate = convertDateFormat(originalDate);

            if (newDate !== originalDate) {
                dateCellContent.text(newDate);
                Logger.log(`Formatted ${fieldName}:`, {
                    original: originalDate,
                    formatted: newDate
                });
            }

            return true;
        } catch (error) {
            Logger.error(`Error formatting ${fieldName}:`, error);
            return false;
        }
    }

    /**
     * Main function to format the table
     * @param {number} retryCount - Number of retry attempts
     * @returns {Promise} - Resolves when formatting is complete
     */
    async function formatTable(retryCount = 0) {
        try {
            Logger.log('Starting table formatting...');

            const table = $(`#${CONFIG.tableId}`);
            if (!validateTable(table)) {
                if (retryCount < CONFIG.maxRetries) {
                    Logger.log(`Retry attempt ${retryCount + 1} of ${CONFIG.maxRetries}`);
                    await new Promise(resolve => setTimeout(resolve, CONFIG.retryDelay));
                    return formatTable(retryCount + 1);
                }
                throw new Error('Table validation failed after max retries');
            }

            const formattingResults = CONFIG.dateFields.map(fieldName => 
                formatDateField(table, fieldName)
            );

            const successCount = formattingResults.filter(Boolean).length;
            Logger.log(`Table formatting completed. ${successCount}/${CONFIG.dateFields.length} fields processed`);

            return true;
        } catch (error) {
            Logger.error('Error in formatTable:', error);
            return false;
        }
    }

    // Initialize the formatter
    Logger.log('Initializing table formatter...');
    formatTable().then(success => {
        Logger.log(`Table formatter initialization ${success ? 'successful' : 'failed'}`);
    });
});
