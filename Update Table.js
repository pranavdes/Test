/**
 * Confluence Table and Iframe Handler
 * Version: 2.0.0
 * Purpose: Format tables and handle iframe content in Confluence pages
 * 
 * Commit Message: Complete implementation with table formatting and iframe handling
 * Changes:
 * - Combined table formatting and iframe handling
 * - Added comprehensive error handling and logging
 * - Improved code organization and documentation
 */

AJS.toInit(function($) {
    // Enable debug mode for development
    const DEBUG = true;

    // Configuration object for easy maintenance
    const CONFIG = {
        tableId: "Ownership\\&Scope",
        dateFields: ["SOP Next Review Date", "Last Review Date"],
        reviewerField: "Last Reviewed By",
        maxRetries: 3,
        retryDelay: 1000, // milliseconds
        dummyDate: "1970-01-01",
        iframe: {
            maxAttempts: 10,
            checkInterval: 500, // milliseconds
            selectors: {
                durationFormat: 'div[class^="FieldDuration_formatSelector"]'
            }
        }
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
     * Converts date format to a standardized string
     * @param {string} dateString - The date string to convert
     * @returns {string} - Formatted date string or empty string if invalid
     */
    function convertDateFormat(dateString) {
        try {
            // Handle empty or dummy date
            if (!dateString || !dateString.trim() || dateString.trim() === CONFIG.dummyDate) {
                Logger.log('Empty or dummy date received');
                return '';
            }

            // Try parsing the date
            const date = new Date(dateString);
            
            // Check if date is valid
            if (isNaN(date.getTime())) {
                Logger.error('Invalid date format:', dateString);
                return dateString; // Return original if parsing fails
            }

            // Format the date
            const options = { 
                year: 'numeric', 
                month: 'short', 
                day: '2-digit',
                timeZone: 'UTC' // Ensure consistent timezone handling
            };

            return date
                .toLocaleDateString('en-US', options)
                .replace(/,/g, '')
                .replace(/(\w+) (\d+) (\d+)/, '$1 $2, $3');

        } catch (error) {
            Logger.error('Error in convertDateFormat:', error);
            return dateString; // Return original string if conversion fails
        }
    }

    /**
     * Formats the reviewer field by removing brackets and '~' character
     * @param {jQuery} reviewerCell - jQuery element containing reviewer information
     */
    function formatReviewer(reviewerCell) {
        try {
            if (!reviewerCell || !reviewerCell.length) {
                Logger.error('Reviewer cell not found');
                return;
            }

            let reviewerContent = reviewerCell.html();
            if (reviewerContent) {
                // Remove [~ and ] from reviewer content
                reviewerContent = reviewerContent.replace(/^\[~/, '').replace(/\]$/, '');
                reviewerCell.html(reviewerContent);
                Logger.log('Reviewer field formatted successfully');
            }
        } catch (error) {
            Logger.error('Error formatting reviewer:', error);
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

            Logger.log(`Processing ${fieldName}:`, {
                original: originalDate,
                formatted: newDate
            });

            if (newDate !== originalDate) {
                dateCellContent.text(newDate);
                Logger.log(`Formatted ${fieldName} successfully`);
            }

            return true;
        } catch (error) {
            Logger.error(`Error formatting ${fieldName}:`, error);
            return false;
        }
    }

    /**
     * Handles hiding the duration selector in the iframe
     * @param {HTMLIFrameElement} iframe - The iframe element
     */
    function hideDurationSelector(iframe) {
        try {
            const $iframe = $(iframe);
            const $iframeContent = $iframe.contents();
            const $durationSelector = $iframeContent.find('div[class^="FieldDuration_formatSelector"]');
            
            if ($durationSelector.length) {
                $durationSelector.hide();
                Logger.log('Successfully hid duration selector');
            } else {
                Logger.error('Duration selector not found in iframe');
            }
        } catch (error) {
            Logger.error('Error hiding duration selector:', error);
        }
    }

    /**
     * Waits for iframe content to be ready
     * @param {HTMLIFrameElement} iframe - The iframe element
     * @returns {Promise} - Resolves when content is ready
     */
    function waitForIframeContent(iframe) {
        return new Promise((resolve, reject) => {
            let attempts = 0;
            
            const checkContent = () => {
                try {
                    const $iframe = $(iframe);
                    const $iframeContent = $iframe.contents();
                    const $body = $iframeContent.find('body');
                    
                    if ($body.length) {
                        resolve(iframe);
                    } else if (attempts < CONFIG.iframe.maxAttempts) {
                        attempts++;
                        setTimeout(checkContent, CONFIG.iframe.checkInterval);
                    } else {
                        reject(new Error('Iframe content not loaded after max attempts'));
                    }
                } catch (error) {
                    reject(error);
                }
            };
            
            checkContent();
        });
    }

    /**
     * Sets up iframe observers and handlers
     */
    function setupIframeHandlers() {
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.addedNodes) {
                    mutation.addedNodes.forEach((node) => {
                        if (node.tagName === 'IFRAME') {
                            Logger.log('New iframe detected');
                            
                            $(node).on('load', function() {
                                waitForIframeContent(this)
                                    .then((iframe) => {
                                        hideDurationSelector(iframe);
                                    })
                                    .catch((error) => {
                                        Logger.error('Error handling iframe:', error);
                                    });
                            });
                        }
                    });
                }
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        Logger.log('Iframe handlers setup complete');
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

            // Format date fields
            const formattingResults = CONFIG.dateFields.map(fieldName => 
                formatDateField(table, fieldName)
            );

            // Format reviewer field
            const reviewerRow = table.find(`th span:contains("${CONFIG.reviewerField}")`).closest('tr');
            if (reviewerRow.length) {
                const reviewerCell = reviewerRow.find('td p span span');
                formatReviewer(reviewerCell);
            } else {
                Logger.error('Reviewer row not found');
            }

            const successCount = formattingResults.filter(Boolean).length;
            Logger.log(`Table formatting completed. ${successCount}/${CONFIG.dateFields.length} fields processed`);

            return true;
        } catch (error) {
            Logger.error('Error in formatTable:', error);
            return false;
        }
    }

    /**
     * Initialize all functionality
     */
    async function initializeAll() {
        try {
            // Initialize table formatting
            await formatTable();
            
            // Setup iframe handlers
            setupIframeHandlers();
            
            Logger.log('All initializations complete');
        } catch (error) {
            Logger.error('Error during initialization:', error);
        }
    }

    // Start initialization
    initializeAll();
});
