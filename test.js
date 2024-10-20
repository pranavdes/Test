AJS.toInit(function($) {
    console.log("Refined Ownership & Scope table formatter script initialized");

    const TABLE_ID = "Ownership\\&Scope"; // Escaped ampersand
    const DATE_FIELD_NAME = "SOP Next Review Date";
    const REVIEWER_FIELD_NAME = "Last Reviewed By";
    const DIALOG_TRIGGER_CLASS = "cw-byline__dialog-trigger";
    const DUMMY_DATE = "2025-01-01";
    const PARAMETERS_DIALOG_ID = "cw-parametersDialog_content";

    function convertDateFormat(dateString) {
        if (!dateString.trim() || dateString.trim() === DUMMY_DATE) {
            return ''; // Return empty string for blank dates or dummy date
        }
        const date = new Date(dateString);
        if (isNaN(date.getTime())) {
            return dateString; // Return original string if it's an invalid date
        }
        const options = { year: 'numeric', month: 'short', day: '2-digit' };
        return date.toLocaleDateString('en-US', options).replace(/(\w+) (\d+), (\d+)/, '$1 $2, $3,');
    }

    function getNextYearDate() {
        const today = new Date();
        today.setFullYear(today.getFullYear() + 1);
        return today;
    }

    function formatDateYYYYMMDD(date) {
        return date.toISOString().split('T')[0];
    }

    function formatTable() {
        const table = $(`#${TABLE_ID}`);
        if (table.length) {
            console.log("Table found, processing...");

            // Process SOP Next Review Date
            const dateRow = table.find('th span:contains("' + DATE_FIELD_NAME + '")').closest('tr');
            if (dateRow.length) {
                const dateCell = dateRow.find('td span span span');
                const originalDate = dateCell.text().trim();
                const newDate = convertDateFormat(originalDate);
                dateCell.text(newDate);
                console.log("Date converted:", originalDate, "to", newDate);
            } else {
                console.log("SOP Next Review Date row not found");
            }

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

        // Initially disable all buttons
        $buttons.prop('disabled', true);

        // Function to check comment validity
        function isValidComment(comment) {
            return comment.trim().length > 0 && !/^\s*$/.test(comment);
        }

        // Event listener for textarea
        $textarea.on('input', function() {
            const isValid = isValidComment($(this).val());
            $buttons.prop('disabled', !isValid);
        });

        console.log("Comment iframe content initialized");
    }

    function handleParametersDialog() {
        // We'll use MutationObserver to detect when the parameters dialog is added to the DOM
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
                const $dateInput = $iframeContent.find('input[id$="-uid3-input"]');
                const $dateDisplay = $iframeContent.find('div.css-shaw93-singleValue');

                if ($dateInput.length && $dateDisplay.length) {
                    console.log("Parameters iframe content found");
                    clearInterval(checkInterval);
                    updateParametersDialogContent($iframeContent);
                    return false; // Break the each loop
                }
            });
        }, 100); // Check every 100ms

        // Stop checking after 30 seconds to prevent infinite loop
        setTimeout(() => {
            clearInterval(checkInterval);
            console.log("Parameters iframe content not found after 30 seconds");
        }, 30000);
    }

    function updateParametersDialogContent($iframeContent) {
        const $dateInput = $iframeContent.find('input[id$="-uid3-input"]');
        const $dateDisplay = $iframeContent.find('div.css-shaw93-singleValue');
        const $formatSelectorDiv = $iframeContent.find('div[class^="FieldDuration_formatSelector"]');

        if ($dateInput.length && $dateDisplay.length) {
            const nextYear = getNextYearDate();
            const formattedDate = formatDateYYYYMMDD(nextYear);
            const displayDate = convertDateFormat(formattedDate);

            $dateInput.val(formattedDate).trigger('change');
            $dateDisplay.text(displayDate);
            console.log("SOP Next Review Date updated in parameters dialog");
        } else {
            console.log("Date input or display not found in parameters dialog");
        }

        if ($formatSelectorDiv.length) {
            $formatSelectorDiv.hide();
            console.log("Format selector hidden in parameters dialog");
        } else {
            console.log("Format selector not found in parameters dialog");
        }
    }

    function initialize() {
        formatTable();
        handleCommentDialog();
        handleParametersDialog();
    }

    // Wait for the table to load
    function waitForTable() {
        if ($(`#${TABLE_ID}`).length) {
            console.log("Table found, initializing...");
            initialize();
        } else {
            console.log("Table not found, retrying in 500ms...");
            setTimeout(waitForTable, 500);
        }
    }

    // Start the process
    waitForTable();
});

console.log("Refined Ownership & Scope table formatter script loaded");