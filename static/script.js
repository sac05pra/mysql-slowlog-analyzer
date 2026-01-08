document.addEventListener('DOMContentLoaded', () => {
    
    // Element definitions
    const form = document.getElementById('analysis-form');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = document.getElementById('btn-text');
    const btnSpinner = document.getElementById('btn-spinner');
    const statusContainer = document.getElementById('status-container');
    const statusMessage = document.getElementById('status-message');
    const resultsContainer = document.getElementById('results-container');

    let pollingInterval;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Reset UI
        resultsContainer.innerHTML = '';
        resultsContainer.classList.add('d-none');
        statusContainer.classList.remove('d-none');
        statusMessage.textContent = 'Submitting job...';
        statusMessage.classList.remove('text-danger');
        if (pollingInterval) clearInterval(pollingInterval);
        
        const selectElement = document.getElementById('db-instances');
        const instances = Array.from(selectElement.selectedOptions).map(opt => opt.value);
        const startDate = document.getElementById('start-date').value;
        const endDate = document.getElementById('end-date').value;

        if (instances.length === 0) {
            alert('Please select at least one DB instance.');
            return;
        }

        submitBtn.disabled = true;
        btnText.textContent = 'Processing...';
        btnSpinner.classList.remove('d-none');

        try {
            const response = await fetch('/start-analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ instances, startDate, endDate }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to start analysis job.');
            }

            const data = await response.json();
            pollStatus(data.jobId);

        } catch (error) {
            showError(error.message);
        }
    });

    function pollStatus(jobId) {
        pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`/status/${jobId}`);
                if (!response.ok) throw new Error('Could not fetch job status.');
                
                const data = await response.json();
                statusMessage.textContent = data.status;

                if (data.status === 'Completed' || data.status.startsWith('Error')) {
                    clearInterval(pollingInterval);
                    resetButton();
                    statusContainer.classList.add('d-none');
                    if (data.status === 'Completed') {
                        displayResults(data.reports);
                    } else {
                        showError(data.status);
                    }
                }
            } catch (error) {
                clearInterval(pollingInterval);
                showError(error.message);
                resetButton();
            }
        }, 3000);
    }
    
    async function displayResults(reports) {
        resultsContainer.classList.remove('d-none');

        if (reports.length === 0) {
            resultsContainer.innerHTML = `<div class="card"><div class="card-body">No reports were generated. This might mean no slow logs were found in the date range.</div></div>`;
            return;
        }

        for (const report of reports) {
            try {
                const response = await fetch(`/report/${report.file}`);
                const reportText = await response.text();

                // The button no longer has a spinner, as its action is now instant.
                const reportCard = document.createElement('div');
                reportCard.className = 'card mb-4 shadow-sm';
                reportCard.innerHTML = `
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div>Report for: <strong>${report.instance}</strong></div>
                        <button class="btn btn-success btn-sm btn-analyze">
                           Analyze in New Tab
                        </button>
                    </div>
                    <div class="card-body">
                        <pre><code class="language-bash">${reportText}</code></pre>
                    </div>
                `;
                resultsContainer.appendChild(reportCard);
            } catch (error) {
                console.error(`Failed to load report for ${report.instance}`, error);
            }
        }
        Prism.highlightAll();
    }

    // --- MODIFIED: Event listener for "Analyze with AI" buttons ---
    // This function is now much simpler. Its only job is to save the report
    // data to session storage and open the new analysis page.
    resultsContainer.addEventListener('click', (e) => {
        // Use .closest() to find the button, even if a child span was clicked.
        const aiButton = e.target.closest('.btn-analyze');
    
        // If a click happened but not on our button or inside it, do nothing.
        if (!aiButton) {
            return;
        }
    
        // 1. Get the raw report text from the card
        const reportCard = aiButton.closest('.card');
        const reportText = reportCard.querySelector('pre code').textContent;
    
        // 2. Store it in the browser's session storage. This data will be
        //    available to the new tab we are about to open.
        sessionStorage.setItem('reportForAnalysis', reportText);
    
        // 3. Open the new analysis page in a new browser tab.
        window.open('/analysis', '_blank');
    });

    // Helper functions
    function showError(message) {
        statusContainer.classList.add('d-none');
        resultsContainer.classList.remove('d-none');
        resultsContainer.innerHTML = `<div class="alert alert-danger">${message}</div>`;
        resetButton();
    }

    function resetButton() {
        submitBtn.disabled = false;
        btnText.textContent = 'Start Analysis';
        btnSpinner.classList.add('d-none');
    }
});
