/**
 * Confluence Formatter Module
 * Version: 2.2.0
 * Purpose: Format tables and handle iframe content in Confluence pages
 * 
 * Commit Message: Complete implementation with fixed iframe handling
 * Changes:
 * - Fixed iframe detection and handling timing
 * - Improved event handling for dialog triggers
 * - Enhanced error handling and logging
 */

AJS.toInit(function($) {
    // Enable debug mode for development
    const DEBUG = true;

    // Configuration object for easy maintenance
    const CONFIG = {
        // Table formatting config
        tableId: "Ownership\\&Scope",
        dateFields: ["SOP Next Review Date", "Last Review Date"],
        reviewerField: "Last Reviewed By",
        maxRetries: 3,
        retryDelay: 1000, // milliseconds
        dummyDate: "1970-01-01",
        
        // Iframe handling config
        dialogTriggerClass: 'cw-byline__dialog-trigger',
        iframe: {
            maxAttempts: 20,
            checkInterval: 250, // milliseconds
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
     */
    function convertDateFormat(dateString) {
        try {
            if (!dateString || !dateString.trim() || dateString.trim() === CONFIG.dummyDate) {
                Logger.log('Empty or dummy date received');
                return '';
            }

            const date = new Date(dateString);
            
            if (isNaN(date.getTime())) {
                Logger.error('Invalid date format:', dateString);
                return dateString;
            }

            const options = { 
                year: 'numeric', 
                month: 'short', 
                day: '2-digit',
                timeZone: 'UTC'
            };

            return date
                .toLocaleDateString('en-US', options)
                .replace(/,/g, '')
                .replace(/(\w+) (\d+) (\d+)/, '$1 $2, $3');

        } catch (error) {
            Logger.error('Error in convertDateFormat:', error);
            return dateString;
        }
    }

    /**
     * Formats the reviewer field
     */
    function formatReviewer(reviewerCell) {
        try {
            if (!reviewerCell || !reviewerCell.length) {
                Logger.error('Reviewer cell not found');
                return;
            }

            let reviewerContent = reviewerCell.html();
            if (reviewerContent) {
                reviewerContent = reviewerContent.replace(/^\[~/, '').replace(/\]$/, '');
                reviewerCell.html(reviewerContent);
                Logger.log('Reviewer field formatted successfully');
            }
        } catch (error) {
            Logger.error('Error formatting reviewer:', error);
        }
    }

    /**
     * Validates table elements
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
     * Formats a single date field
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
     * Main table formatting function
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
     * Handles hiding the duration selector in the iframe
     */
    function hideDurationSelector(iframe) {
        return new Promise((resolve) => {
            try {
                const $iframe = $(iframe);
                const $iframeContent = $iframe.contents();
                const $durationSelector = $iframeContent.find('div[class^="FieldDuration_formatSelector"]');
                
                if ($durationSelector.length) {
                    Logger.log('Found duration selector, hiding it');
                    $durationSelector.hide();
                    Logger.log('Successfully hid duration selector');
                    resolve(true);
                } else {
                    Logger.log('Duration selector not found yet');
                    resolve(false);
                }
            } catch (error) {
                Logger.error('Error in hideDurationSelector:', error);
                resolve(false);
            }
        });
    }

    /**
     * Waits for iframe content to be ready
     */
    function waitForIframeContent(iframe) {
        return new Promise((resolve) => {
            let attempts = 0;
            
            function checkContent() {
                if (attempts >= CONFIG.iframe.maxAttempts) {
                    Logger.log('Max attempts reached waiting for iframe content');
                    resolve(false);
                    return;
                }

                try {
                    hideDurationSelector(iframe).then(success => {
                        if (success) {
                            resolve(true);
                        } else {
                            attempts++;
                            setTimeout(checkContent, CONFIG.iframe.checkInterval);
                        }
                    });
                } catch (error) {
                    Logger.error('Error checking iframe content:', error);
                    attempts++;
                    setTimeout(checkContent, CONFIG.iframe.checkInterval);
                }
            }

            checkContent();
        });
    }

    /**
     * Handles dialog trigger clicks
     */
    function handleDialogTrigger() {
        Logger.log('Dialog trigger clicked, starting iframe watch');
        
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.addedNodes.length) {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeName === 'IFRAME') {
                            Logger.log('New iframe detected');
                            const iframe = node;
                            
                            $(iframe).on('load', function() {
                                Logger.log('Iframe loaded, waiting for content');
                                waitForIframeContent(this).then(success => {
                                    if (success) {
                                        Logger.log('Successfully processed iframe content');
                                    } else {
                                        Logger.error('Failed to process iframe content');
                                    }
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

        setTimeout(() => {
            observer.disconnect();
            Logger.log('Stopped observing for new iframes');
        }, 10000);
    }

    /**
     * Initialize iframe handling
     */
    function initializeIframeHandling() {
        $(document).off('click', '.' + CONFIG.dialogTriggerClass);
        
        $(document).on('click', '.' + CONFIG.dialogTriggerClass, function(e) {
            Logger.log('Dialog trigger clicked');
            handleDialogTrigger();
        });

        Logger.log('Dialog trigger handlers initialized');
    }

    /**
     * Initialize all functionality
     */
    async function initializeAll() {
        try {
            Logger.log('Starting initialization...');
            await formatTable();
            initializeIframeHandling();
            Logger.log('All initializations complete');
        } catch (error) {
            Logger.error('Error during initialization:', error);
        }
    }

    // Start initialization
    initializeAll();
});
