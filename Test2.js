AJS.toInit(function($) {
    console.log("Complete Ownership & Scope table formatter script initialized");

    // Constants
    const TABLE_ID = "Ownership\\&Scope";
    const DATE_FIELDS = ["SOP Next Review Date", "Last Review Date"];
    const REVIEWER_FIELD_NAME = "Last Reviewed By";
    const DIALOG_TRIGGER_CLASS = "cw-byline__dialog-trigger";
    const DUMMY_DATE = "1970-01-01";
    const BUTTONS_CONTAINER_SELECTOR = 'div[class^="index_buttons"]';

    function convertDateFormat(dateString) {
        if (!dateString.trim() || dateString.trim() === DUMMY_DATE) return '';
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return dateString;
        const options = { year: 'numeric', month: 'short', day: '2-digit' };
        return date.toLocaleDateString('en-US', options)
            .replace(/,/g, '')
            .replace(/(\w+) (\d+) (\d+)/, '$1 $2, $3');
    }

    function formatTable() {
        const table = $(`#${TABLE_ID}`);
        if (!table.length) return console.log("Table not found");

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
    }

    function waitForCommentIframeContent() {
        console.log("Waiting for comment iframe content...");
        let contentInitialized = false;

        // First, set up a listener for ContentService initialization
        const contentObserver = new MutationObserver((mutations, observer) => {
            for (const mutation of mutations) {
                if (mutation.type === 'childList') {
                    const $iframe = $('iframe').filter(function() {
                        return $(this).contents().find('textarea[name="comment"]').length > 0;
                    });

                    if ($iframe.length) {
                        const $iframeContent = $iframe.contents();
                        const $form = $iframeContent.find('form');
                        const $textarea = $form.find('textarea[name="comment"]');
                        const $buttonsContainer = $form.find(BUTTONS_CONTAINER_SELECTOR);

                        if ($form.length && $textarea.length && $buttonsContainer.length) {
                            console.log("Found all required elements, waiting for content initialization");
                            
                            if (!contentInitialized) {
                                const checkInit = setInterval(() => {
                                    // Check if we can find our target elements and if they're properly initialized
                                    const formReady = $form.find('input, textarea, button').length > 0;
                                    
                                    if (formReady) {
                                        clearInterval(checkInit);
                                        contentInitialized = true;
                                        observer.disconnect();
                                        console.log("Content initialization complete");
                                        initializeCommentIframeContent($textarea, $buttonsContainer);
                                    }
                                }, 50);

                                // Set a timeout to prevent infinite checking
                                setTimeout(() => {
                                    clearInterval(checkInit);
                                    if (!contentInitialized) {
                                        console.log("Content initialization timed out");
                                    }
                                }, 5000);
                            }
                            return;
                        }
                    }
                }
            }
        });

        // Start observing
        contentObserver.observe(document.body, {
            childList: true,
            subtree: true
        });

        // Set a timeout to stop observing if nothing happens
        setTimeout(() => {
            contentObserver.disconnect();
            console.log("Comment iframe content not found after timeout");
        }, 30000);
    }

    function initializeCommentIframeContent($textarea, $buttonsContainer) {
        console.log("Initializing comment iframe content");
        const $buttons = $buttonsContainer.find('button');

        function updateButtonState() {
            const isValid = isValidComment($textarea.val());
            console.log("Updating button state, comment is valid:", isValid);
            $buttons.prop('disabled', !isValid);
        }

        function isValidComment(comment) {
            return comment.trim().length > 0 && !/^\s*$/.test(comment);
        }

        // Initial state
        updateButtonState();

        // Remove any existing listeners before adding new ones
        $textarea.off('input').on('input', function() {
            updateButtonState();
        });

        console.log("Comment iframe content initialized");
    }

    function initialize() {
        // Format table first
        formatTable();

        // Set up click handler for the dialog trigger
        $(document).off('click', '.' + DIALOG_TRIGGER_CLASS)
                  .on('click', '.' + DIALOG_TRIGGER_CLASS, function() {
            console.log("Dialog trigger clicked");
            waitForCommentIframeContent();
        });
    }

    // Start the process
    initialize();
});

console.log("Complete Ownership & Scope table formatter script loaded");