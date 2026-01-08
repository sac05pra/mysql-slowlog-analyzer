document.addEventListener('DOMContentLoaded', async () => {
    // Get references to our HTML elements
    const rawReportContainer = document.getElementById('raw-report-container');
    const aiAnalysisContainer = document.getElementById('ai-analysis-container');
    const downloadBtn = document.getElementById('download-zip-btn');

    // This variable will hold the AI's raw Markdown response
    let rawAiAnalysisText = '';
    // This variable holds the raw log report text
    const rawLogReportText = sessionStorage.getItem('reportForAnalysis');

    // --- Main Logic: Load reports and call AI ---

    if (!rawLogReportText) {
        rawReportContainer.innerHTML = '<code class="language-bash">Error: No report data found. Please go back and try again.</code>';
        aiAnalysisContainer.innerHTML = '<div class="alert alert-danger">Could not load report data.</div>';
        return;
    }

    // Display the raw report on the left and highlight it
    rawReportContainer.innerHTML = `<code class="language-bash">${rawLogReportText}</code>`;
    Prism.highlightAll();

    // Call the AI analysis endpoint
    try {
        const response = await fetch('/ai-analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ report_text: rawLogReportText })
        });

        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'An unknown error occurred.');
        }

        // Store the raw Markdown text from the AI
        rawAiAnalysisText = data.analysis;

        // Render the AI's Markdown response into HTML on the right
        aiAnalysisContainer.innerHTML = marked.parse(rawAiAnalysisText);

        // IMPORTANT: Enable the download button now that we have both reports
        downloadBtn.disabled = false;

    } catch (error) {
        console.error('AI Analysis Error:', error);
        aiAnalysisContainer.innerHTML = `<div class="alert alert-danger mb-0"><strong>Error:</strong> ${error.message}</div>`;
        // Keep the button disabled if there's an error
        downloadBtn.disabled = true;
    }


    // --- Event Listener for the Download Button ---

    downloadBtn.addEventListener('click', () => {
        if (!rawLogReportText || !rawAiAnalysisText) {
            alert('Report data is not available to download.');
            return;
        }

        // 1. Create a new JSZip instance
        const zip = new JSZip();

        // 2. Add files to the zip folder
        zip.file("raw_report.txt", rawLogReportText);
        zip.file("ai_analysis.md", rawAiAnalysisText); // Saving as Markdown is more useful

        // 3. Generate the ZIP file asynchronously
        zip.generateAsync({ type: "blob" })
            .then(function(content) {
                // 4. Create a temporary link to trigger the download
                const link = document.createElement('a');
                link.href = URL.createObjectURL(content);
                link.download = "analysis_reports.zip";
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            });
    });
});
