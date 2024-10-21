AJS.toInit(function($) {
    console.log("Revised Ownership & Scope table formatter script initialized");

    const TABLE_ID = "Ownership\\&Scope"; // Escaped ampersand
    const DATE_FIELDS = ["SOP Next Review Date", "Last Review Date"];
    const REVIEWER_FIELD_NAME = "Last Reviewed By";
    const DIALOG_TRIGGER_CLASS = "cw-byline__dialog-trigger";
    const DUMMY_DATE = "1970-01-01";
    const PARAMETERS_DIALOG_ID = "cw-parametersDialog_content";

    function convertDateFormat(dateString) {
        if (!dateString.trim() || dateString.trim() === DUMMY_DATE) {
            return ''; // Return empty string for blank dates or dummy date
        }
        const date = new Date(dateString);
        if (isNaN(date.getTime())) {
            return dateString; // Return original string if it's an invalid date
        }
        const options = { weekday: 'short', year: 'numeric', month: 'short', day: '2-digit' };
        return date.toLocaleDateString('en-US', options);
    }

    function getNextYearDate() {
        const today = new Date();
        today.setFullYear(today.getFullYear() + 1);
        return today;
    }

    function formatTable() {
        const table = $(`#${TABLE_ID}`);
        if (table.length) {
            console.log("Table found, processing...");

            // Process date fields
            DATE_FIELDS.forEach(fieldName => {
                const dateRow = table.find('th span:contains("' + fieldName + '")').closest('tr');
                if (dateRow.length) {
                    const dateCell = dateRow.find('td span span');
                    // Add an extra 'span' selector for 'SOP Next Review Date' if needed
                    const dateCellContent = fieldName === "SOP Next Review Date" ? dateCell.find('span') : dateCell;
                    const originalDate = dateCellContent.text().trim();
                    const newDate = convertDateFormat(originalDate);
                    dateCellContent.text(newDate);
                    console.log(`${fieldName} converted:`, originalDate, "to", newDate);
                } else {
                    console.log(`${fieldName} row not found`);
                }
            });

            // Process Last Reviewed By
            const reviewerRow = table.find('th span:contains("' + REVIEWER_FIELD_NAME + '")').closest('tr');
            if (reviewerRow.length) {
                const reviewerCell = reviewerRow.find('td p span span');
                let reviewerContent = reviewerCell.html();
                reviewerContent = reviewerContent.replace(/^\[~/, '').replace(/\]$/, '');
                reviewerCell.html(reviewerContent);
                console.log("Reviewer field formatted");
            } else {
                console.log("Last Reviewed By row not found");
            }

            console.log("Table processing completed");
        } else {
            console.log("Table not found");
        }
    }

    function handleCommentDialog() {
        $(document).on('click', '.' + DIALOG_TRIGGER_CLASS, function() {
            console.log("Dialog trigger clicked");
            waitForCommentIframeContent();
        });
    }

    function waitForCommentIframeContent() {
        console.log("Waiting for comment iframe content...");
        const checkInterval = setInterval(function() {
            $('iframe').each(function() {
                const $iframe = $(this);
                const $iframeContent = $iframe.contents();
                const $textarea = $iframeContent.find('textarea[name="comment"]');
                const $buttons = $iframeContent.find('button');

                if ($textarea.length && $buttons.length) {
                    console.log("Comment iframe content found");
                    clearInterval(checkInterval);
                    initializeCommentIframeContent($textarea, $buttons);
                    return false; // Break the each loop
                }
            });
        }, 100); // Check every 100ms

        // Stop checking after 30 seconds to prevent infinite loop
        setTimeout(() => {
            clearInterval(checkInterval);
            console.log("Comment iframe content not found after 30 seconds");
        }, 30000);
    }

    function initializeCommentIframeContent($textarea, $buttons) {
        console.log("Initializing comment iframe content");

        function updateButtonState() {
            const isValid = isValidComment($textarea.val());
            $buttons.prop('disabled', !isValid);
        }

        // Function to check comment validity
        function isValidComment(comment) {
            return comment.trim().length > 0 && !/^\s*$/.test(comment);
        }

        // Initially set button state
        updateButtonState();

        // Event listener for textarea
        $textarea.on('input', updateButtonState);

        console.log("Comment iframe content initialized");
    }

    function handleParametersDialog() {
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList') {
                    const $parametersDialog = $(`#${PARAMETERS_DIALOG_ID}`);
                    if ($parametersDialog.length) {
                        observer.disconnect();
                        waitForParametersIframeContent();
                    }
                }
            });
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    function waitForParametersIframeContent() {
        console.log("Waiting for parameters iframe content...");
        const checkInterval = setInterval(function() {
            $('iframe').each(function() {
                const $iframe = $(this);
                const $iframeContent = $iframe.contents();
                
                const $dateLabel = $iframeContent.find('label:contains("SOP Next Review Date")');
                
                if ($dateLabel.length) {
                    console.log("Parameters iframe content found");
                    clearInterval(checkInterval);
                    updateParametersDialogContent($iframeContent);
                    return false; // Break the each loop
                }
            });
        }, 100); // Check every 100ms

        setTimeout(() => {
            clearInterval(checkInterval);
            console.log("Parameters iframe content not found after 30 seconds");
        }, 30000);
    }

    function updateParametersDialogContent($iframeContent) {
        const $dateLabel = $iframeContent.find('label:contains("SOP Next Review Date")');
        if ($dateLabel.length) {
            const $dateContainer = $dateLabel.closest('.index_field__3S2HP');
            const $dateDisplay = $dateContainer.find('.css-shuw93-singleValue');
            const $formatSelectorDiv = $dateContainer.find('div[class^="FieldDuration_formatSelector"]');

            if ($dateDisplay.length) {
                const nextYear = getNextYearDate();
                const formattedDate = convertDateFormat(nextYear.toISOString());

                // Update only the visible text
                $dateDisplay.text(formattedDate);

                // Set up an observer to maintain our formatted date
                setupDateObserver($dateContainer, formattedDate);

                console.log("SOP Next Review Date display updated in parameters dialog");
            } else {
                console.log("Date display not found in parameters dialog");
            }

            if ($formatSelectorDiv.length) {
                $formatSelectorDiv.hide();
                console.log("Format selector hidden in parameters dialog");
            } else {
                console.log("Format selector not found in parameters dialog");
            }
        } else {
            console.log("SOP Next Review Date label not found in parameters dialog");
        }
    }

    function setupDateObserver($dateContainer, formattedDate) {
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList' || mutation.type === 'characterData') {
                    const $dateDisplay = $dateContainer.find('.css-shuw93-singleValue');
                    if ($dateDisplay.text() !== formattedDate) {
                        $dateDisplay.text(formattedDate);
                    }
                }
            });
        });

        observer.observe($dateContainer[0], { 
            childList: true, 
            subtree: true, 
            characterData: true 
        });
    }

    function initialize() {
        formatTable();
        handleCommentDialog();
        handleParametersDialog();
    }

    function waitForTable() {
        if ($(`#${TABLE_ID}`).length) {
            console.log("Table found, initializing...");
            initialize();
        } else {
            console.log("Table not found, retrying in 500ms...");
            setTimeout(waitForTable, 500);
        }
    }

    waitForTable();
});

console.log("Revised Ownership & Scope table formatter script loaded");