// static/js/script.js

document.addEventListener('DOMContentLoaded', function() {
    // --- GLOBAL STATE ---
    let probabilityBarChart = null;
    let conditionalProbChart = null; // Chart for the new feature
    let fullProbabilities = {};
    let fullConditionalProbs = {}; // Data for the new feature
    let currentTotals = {};
    let currentTestType = 'Single';

    // --- CHARTING LOGIC ---
    function getThemeColors() {
        const theme = document.body.className.includes('theme-dark') ? 'dark' : (document.body.className.includes('theme-tokyo') ? 'tokyo' : 'light');
        const palettes = {
            light: { text: '#212529', border: '#dee2e6', bar_s: '#0d6efd', bar_m: '#198754', kde: '#dc3545', hist: 'rgba(13, 110, 253, 0.5)' },
            dark: { text: '#c9d1d9', border: '#30363d', bar_s: '#FF9900', bar_m: '#2da44e', kde: '#f85149', hist: 'rgba(255, 153, 0, 0.4)' },
            tokyo: { text: '#c0caf5', border: '#414868', bar_s: '#7aa2f7', bar_m: '#9ece6a', kde: '#f7768e', hist: 'rgba(122, 162, 247, 0.5)' }
        };
        return palettes[theme];
    }

    // Chart renderer for the MAIN probability chart
    function renderProbabilityBarChart(probData, testType) {
        const canvas = document.getElementById('probability-chart-canvas');
        if (!canvas) return;
        if (probabilityBarChart) probabilityBarChart.destroy();
        
        if (!probData || probData.length === 0) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const colors = getThemeColors();
            ctx.textAlign = 'center';
            ctx.fillStyle = colors.text;
            ctx.fillText('No data available for this filter.', canvas.width / 2, canvas.height / 2);
            probabilityBarChart = null;
            return;
        }

        const colors = getThemeColors();
        const barColor = testType === 'Mind' ? colors.bar_m : colors.bar_s;
        
        probData.sort((a, b) => b.probability - a.probability);
        const labels = probData.map(p => p.state);
        const values = probData.map(p => p.probability);
        
        const chartContainer = canvas.parentElement;
        chartContainer.style.height = `${Math.max(400, labels.length * 38)}px`;

        probabilityBarChart = new Chart(canvas, {
            type: 'bar',
            data: { 
                labels: labels, 
                datasets: [{
                    label: 'Probability', data: values, backgroundColor: barColor,
                    borderColor: barColor, barThickness: 'flex', maxBarThickness: 25
                }] 
            },
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { beginAtZero: true, max: 100, ticks: { color: colors.text }, grid: { color: colors.border }, title: { display: true, text: 'Probability (%)', color: colors.text } },
                    y: { ticks: { color: colors.text }, grid: { display: false } }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.raw.toFixed(2)}%` } },
                    datalabels: {
                        anchor: 'end', align: 'end', color: colors.text,
                        font: { weight: 'bold' },
                        formatter: (value) => value > 1 ? value.toFixed(1) + '%' : ''
                    }
                }
            }
        });
    }

    // NEW: Chart renderer for the CONDITIONAL (by starting zone) chart
    function renderConditionalBarChart(probData) {
        const canvas = document.getElementById('conditional-chart-canvas');
        if (!canvas) return;
        if (conditionalProbChart) conditionalProbChart.destroy();

        if (!probData || probData.length === 0) {
            // No need for a message here, the dropdown simply won't have this option.
            return;
        }

        const colors = getThemeColors();
        probData.sort((a, b) => b.probability - a.probability);
        const labels = probData.map(p => p.state);
        const values = probData.map(p => p.probability);

        const chartContainer = canvas.parentElement;
        chartContainer.style.height = `${Math.max(250, labels.length * 38)}px`;

        conditionalProbChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Probability', data: values, backgroundColor: colors.bar_m, // Use a consistent color
                    borderColor: colors.bar_m, barThickness: 'flex', maxBarThickness: 25
                }]
            },
            options: { // Same options as the main chart
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { beginAtZero: true, max: 100, ticks: { color: colors.text }, grid: { color: colors.border }, title: { display: true, text: 'Probability (%)', color: colors.text } },
                    y: { ticks: { color: colors.text }, grid: { display: false } }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (c) => `End Zone: ${c.label}\nProbability: ${c.raw.toFixed(2)}%` } },
                    datalabels: {
                        anchor: 'end', align: 'end', color: colors.text, font: { weight: 'bold' },
                        formatter: (value) => value > 1 ? value.toFixed(1) + '%' : ''
                    }
                }
            }
        });
    }

    async function handlePdfDownload(e) {
        const btn = e.currentTarget;
        let testId = btn.dataset.testId;
        if (!testId && typeof testData !== 'undefined') { testId = testData.id; }
        if (!testId) { showAlert('Could not determine test ID for PDF generation.', 'danger'); return; }
        if (!probabilityBarChart) { showAlert('Cannot generate PDF. Main chart has no data.', 'warning'); return; }

        btn.disabled = true; btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Generating...`;
        showAlert('Generating chart images for PDF...', 'info', false);

        const whiteBgPlugin = {
            id: 'customCanvasBackgroundColor',
            beforeDraw: (chart, args, options) => {
                const { ctx } = chart;
                ctx.save();
                ctx.globalCompositeOperation = 'destination-over';
                ctx.fillStyle = options.color || '#ffffff';
                ctx.fillRect(0, 0, chart.width, chart.height);
                ctx.restore();
            }
        };

        try {
            Chart.register(whiteBgPlugin);
            probabilityBarChart.options.plugins.customCanvasBackgroundColor = { color: 'white' };
            probabilityBarChart.update();
            const barChartImg = probabilityBarChart.toBase64Image();
            let histogramImg = null;
            // If your histogram is rendered by Chart.js:
            if (typeof histogramChart !== 'undefined' && histogramChart) {
                 histogramImg = histogramChart.toBase64Image();
            }
            const payload = { bar_chart_img: barChartImg,
                              histogram_img: histogramImg // will be null if not present, that's fine
             };
            showAlert('Sending data to server for PDF assembly...', 'info', false);
            const response = await fetch(`/api/pdf/${testId}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
            });
            if (!response.ok) { const errorData = await response.json(); throw new Error(errorData.error || `Server error: ${response.statusText}`); }
            const data = await response.json();
            if (data.error) throw new Error(data.error);
            showAlert('Successfully generated PDF, download will begin.', 'success');
            const link = document.createElement('a');
            link.href = `data:application/pdf;base64,${data.pdf_data}`;
            let testName = (typeof testData !== 'undefined' ? testData.test_name : document.getElementById('test-name').value) || `report`;
            link.download = `backtest_report_${testName.replace(/\s+/g, '_')}_${testId}.pdf`;
            link.click();
        } catch (error) {
            showAlert(`PDF generation failed: ${error.message}`, 'danger', false);
        } finally {
            Chart.unregister(whiteBgPlugin);
            if (probabilityBarChart) { delete probabilityBarChart.options.plugins.customCanvasBackgroundColor; probabilityBarChart.update(); }
            btn.disabled = false; btn.innerHTML = `<i class="bi bi-file-earmark-pdf-fill"></i> PDF`;
        }
    }

    function updateTable(filter) {
        const tableContainer = document.getElementById('probability-table-container');
        if(!tableContainer) return;
        const badgeClass = currentTestType === 'Mind' ? 'bg-success-custom' : 'bg-primary-custom';
        const total = currentTotals[filter];
        const data = fullProbabilities[filter];
        
        let tableHtml = `<p class="lead mt-4">Based on <strong>${total || 0}</strong> historical match(es) for this filter:</p>
                         <table class="table table-sm"><thead><tr><th>Outcome</th><th class="text-end">Probability</th></tr></thead><tbody>`;
        if (data && data.length > 0) {
            data.sort((a,b) => b.probability - a.probability);
            data.forEach(p => { 
                tableHtml += `<tr><td>${p.state}</td><td class="text-end"><span class="badge ${badgeClass} rounded-pill">${p.probability.toFixed(2)}%</span></td></tr>`; 
            });
        } else {
            tableHtml += `<tr><td colspan="2" class="text-center text-muted">No outcomes for this filter.</td></tr>`;
        }
        tableContainer.innerHTML = tableHtml + '</tbody></table>';
    }
    
    function showResults(resultsData, testType, params) {
        if (!document.getElementById('results-container')) return;
        document.getElementById('results-placeholder')?.classList.add('d-none');
        document.getElementById('results-container').classList.remove('d-none');
        
        currentTestType = testType;
        fullProbabilities = resultsData.probabilities;
        fullConditionalProbs = resultsData.probabilities_by_start_zone || {};
        currentTotals = resultsData.totals;

        if (testType === 'Single') {
            document.getElementById('results-title').textContent = `Single Test: ${params.ticker}`;
            const historyContainer = document.getElementById('history-container');
            if (historyContainer && resultsData.history?.length > 0) {
                historyContainer.classList.remove('d-none');
                document.getElementById('history-title').textContent = 'Historical Matches';
                let table = `<table class="table table-sm table-striped"><thead><tr><th>Pattern End</th><th>Outcome Date</th><th>Outcome State</th></tr></thead><tbody>`;
                resultsData.history.forEach(h => { table += `<tr><td>${h.premise_date}</td><td>${h.outcome_date}</td><td>${h.state}</td></tr>`; });
                document.getElementById('history-table-container').innerHTML = table + '</tbody></table>';
            } else if (historyContainer) {
                historyContainer.classList.add('d-none');
            }
        } else {
            document.getElementById('results-title').textContent = 'Market-Wide Analysis (Mind)';
            const historyContainer = document.getElementById('history-container');
            if(historyContainer) historyContainer.classList.add('d-none');
        }
        
        document.querySelector('#chart-filter-controls button[data-filter="all"]')?.click();
        
        const pdfBtn = document.getElementById('pdf-download-btn');
        if (pdfBtn) {
            pdfBtn.dataset.testId = resultsData.test_id;
            pdfBtn.classList.remove('d-none');
            const newPdfBtn = pdfBtn.cloneNode(true);
            pdfBtn.parentNode.replaceChild(newPdfBtn, pdfBtn);
            newPdfBtn.addEventListener('click', handlePdfDownload);
        }

        const conditionalCard = document.getElementById('conditional-chart-card');
        const selector = document.getElementById('start-zone-selector');
        const startZones = Object.keys(fullConditionalProbs);
        
        if (conditionalCard && selector && startZones.length > 0) {
            conditionalCard.classList.remove('d-none');
            selector.innerHTML = '';
            startZones.sort().forEach(zone => {
                selector.add(new Option(zone, zone));
            });
            selector.onchange = () => {
                const selectedZone = selector.value;
                const data = fullConditionalProbs[selectedZone];
                renderConditionalBarChart(data);
            };
            selector.dispatchEvent(new Event('change'));
        } else if (conditionalCard) {
            conditionalCard.classList.add('d-none');
        }
    }

    function initIndexPage() {
        setInitialDates(); fetchTickers(); fetchStockUniverses();
        document.getElementById('backtest-form')?.addEventListener('submit', handleSingleBacktestSubmit);
        document.getElementById('run-mind-btn')?.addEventListener('click', handleCamarillaMindClick);
        document.getElementById('import-btn')?.addEventListener('click', () => document.getElementById('import-file-input').click());
        document.getElementById('import-file-input')?.addEventListener('change', handleFileImport);
        const params = new URLSearchParams(window.location.search);
        const testIdToView = params.get('view_test_id');
        if (testIdToView) { loadSpecificTestForView(testIdToView); }
    }

    function initHistoryPage() { fetchHistory(); }
    
    function initViewPage() {
        if (typeof testData === 'undefined') return;
        const results = JSON.parse(testData.results);
        const params = JSON.parse(testData.parameters);
        
        let infoHtml = `<p class="mb-1"><strong>Pattern:</strong> <code class="text-muted">${testData.pattern}</code></p>
                        <p class="mb-1"><strong>Date Range:</strong> ${params.start_date} to ${params.end_date}</p>`;
        if(testData.notes) infoHtml += `<p class="mb-0"><strong>Notes:</strong> <em>${testData.notes}</em></p>`;
        document.getElementById('test-info').innerHTML = infoHtml;
        
        showResults(results, testData.test_type, params);

        document.getElementById('export-btn').addEventListener('click', () => { window.location.href = `/api/export_test/${testData.id}`; });
        document.getElementById('share-whatsapp').href = `https://api.whatsapp.com/send?text=${encodeURIComponent(`Camarilla Backtest: ${testData.test_name}\n${window.location.href}`)}`;
        document.getElementById('share-email').href = `mailto:?subject=${encodeURIComponent(`Camarilla Backtest: ${testData.test_name}`)}&body=${encodeURIComponent("View the backtest report here:\n" + window.location.href)}`;
    }

    function initializeApp() {
        document.getElementById('chart-filter-controls')?.addEventListener('click', (e) => {
            if (e.target.tagName === 'BUTTON' && fullProbabilities.all) {
                const filter = e.target.dataset.filter;
                document.querySelectorAll('#chart-filter-controls button').forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                renderProbabilityBarChart(fullProbabilities[filter], currentTestType);
                updateTable(filter);
            }
        });
        
        window.addEventListener('themeChanged', () => {
             if (probabilityBarChart) {
                 const activeFilter = document.querySelector('#chart-filter-controls button.active')?.dataset.filter || 'all';
                 renderProbabilityBarChart(fullProbabilities[activeFilter], currentTestType);
             }
             if (conditionalProbChart) {
                const selector = document.getElementById('start-zone-selector');
                if (selector && selector.value) {
                    renderConditionalBarChart(fullConditionalProbs[selector.value]);
                }
             }
        });

        const copyShareLinkBtn = document.getElementById('copyShareLinkBtn');
        if (copyShareLinkBtn) {
            copyShareLinkBtn.addEventListener('click', () => {
                const shareLinkInput = document.getElementById('shareLinkInput');
                shareLinkInput.select(); document.execCommand('copy');
                copyShareLinkBtn.textContent = 'Copied!';
                setTimeout(() => { copyShareLinkBtn.textContent = 'Copy Link'; }, 2000);
            });
        }
        
        if (document.getElementById('backtest-form')) { initIndexPage(); } 
        else if (document.getElementById('history-table-body')) { initHistoryPage(); } 
        else if (typeof testData !== 'undefined') { initViewPage(); }
    }

    function showAlert(message, type = 'info', autoDismiss = true) { const alertContainer = document.getElementById('alert-container'); if(!alertContainer) return; const wrapper = document.createElement('div'); wrapper.innerHTML = `<div class="alert alert-${type} alert-dismissible fade show" role="alert"><div>${message}</div><button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>`; alertContainer.innerHTML = ''; alertContainer.append(wrapper); if (autoDismiss && type !== 'danger') { setTimeout(() => { wrapper.querySelector('.alert')?.classList.remove('show'); }, 5000); } }
    function setInitialDates() { const today = new Date(); const pastDate = new Date(); pastDate.setFullYear(today.getFullYear() - 10); document.getElementById('end-date').value = today.toISOString().split('T')[0]; document.getElementById('start-date').value = pastDate.toISOString().split('T')[0]; }
    function fetchTickers() { fetch('/api/get_tickers').then(r => r.json()).then(d => { const s = document.getElementById('ticker'); if(s) d.forEach(t => s.add(new Option(t,t))); }).catch(e => showAlert(`Failed to load tickers: ${e.message}`, 'danger')); }
    function fetchStockUniverses() { fetch('/api/get_stock_universes').then(r => r.json()).then(d => { const s = document.getElementById('stock-universe'); if(s) for (const n in d) { s.add(new Option(n,n)); } }).catch(e => showAlert(`Failed to load universes: ${e.message}`, 'danger')); }
    function handleSingleBacktestSubmit(event) { event.preventDefault(); const payload = getFormParams(); payload.ticker = document.getElementById('ticker').value; handleApiCall('/api/run_backtest', payload, 'run-single-btn', (d) => showResults(d, 'Single', payload)); }
    function handleCamarillaMindClick() { const payload = getFormParams(); payload.universe = document.getElementById('stock-universe').value; handleApiCall('/api/run_camarilla_mind', payload, 'run-mind-btn', (d) => showResults(d, 'Mind', payload)); }
    function handleFileImport(event) { const file = event.target.files[0]; if (!file) return; const reader = new FileReader(); reader.onload = (e) => { try { const data = JSON.parse(e.target.result); loadTestDataIntoUI(data); showAlert(`Successfully imported test: ${data.test_name}`, 'success'); } catch (error) { showAlert(`Import failed: Invalid file format. ${error.message}`, 'danger'); } }; reader.readAsText(file); event.target.value = ''; }
    function getFormParams() { return { test_name: document.getElementById('test-name').value.trim(), pattern: document.getElementById('pattern').value.trim(), start_date: document.getElementById('start-date').value, end_date: document.getElementById('end-date').value, notes: document.getElementById('notes').value.trim(), }; }
    function handleApiCall(endpoint, payload, buttonId, displayFunction) { document.getElementById('alert-container').innerHTML = ''; document.getElementById('results-placeholder')?.classList.remove('d-none'); document.getElementById('results-container')?.classList.add('d-none'); const btn = document.getElementById(buttonId); const spinner = document.getElementById(btn.dataset.spinnerId); btn.disabled = true; spinner?.classList.remove('d-none'); fetch(endpoint, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) }) .then(r => { if (!r.ok) return r.json().then(e => { throw new Error(e.error || `Server error: ${r.statusText}`) }); return r.json(); }) .then(d => { if (d.error) throw new Error(d.error); if (d.message) showAlert(d.message, 'info'); else displayFunction(d); }) .catch(e => showAlert(e.message, 'danger')) .finally(() => { btn.disabled = false; spinner?.classList.add('d-none'); }); }
    function loadTestDataIntoUI(data) { document.getElementById('test-name').value = data.test_name || ''; document.getElementById('pattern').value = data.pattern || ''; document.getElementById('notes').value = data.notes || ''; if (data.parameters) { document.getElementById('start-date').value = data.parameters.start_date || ''; document.getElementById('end-date').value = data.parameters.end_date || ''; if (data.parameters.ticker) document.getElementById('ticker').value = data.parameters.ticker; if (data.parameters.universe) document.getElementById('stock-universe').value = data.parameters.universe; } if (data.results) { showResults(data.results, data.test_type, data.parameters); } else { document.getElementById('results-placeholder')?.classList.remove('d-none'); document.getElementById('results-container')?.classList.add('d-none'); } }
    function loadSpecificTestForView(testId) { showAlert('Loading test data...', 'info', false); fetch(`/api/get_history_by_id/${testId}`).then(r => r.json()).then(d => { if (d.error) throw new Error(d.error); loadTestDataIntoUI(d); showAlert(`Loaded results for Test ID: ${testId}`, 'success'); }).catch(e => showAlert(`Failed to load test ${testId}: ${e.message}`, 'danger')); }
    function fetchHistory() { const tableBody = document.getElementById('history-table-body'); if (!tableBody) return; fetch('/api/get_history').then(response => response.json()).then(history => { if (history.length === 0) { tableBody.innerHTML = '<tr><td colspan="7" class="text-center">No history found.</td></tr>'; return; } let allRowsData = history; const renderTable = (data) => { tableBody.innerHTML = ''; data.forEach(item => { const results = JSON.parse(item.results); const params = item.parameters ? JSON.parse(item.parameters) : {}; const matchCount = results.total_matches || results.total_historical_matches || 0; let tickerOrUniverse = (item.test_type === 'Single') ? (params.ticker || 'N/A') : (params.universe || 'All Tickers'); const notes = item.notes || ''; const notesDisplay = notes.length > 30 ? `<span title="${notes}">${notes.substring(0, 30)}...</span>` : (notes || '—'); const row = document.createElement('tr'); row.innerHTML = ` <td><a href="/?view_test_id=${item.id}" class="text-decoration-none">${item.test_name}</a></td> <td><span class="badge ${item.test_type === 'Single' ? 'bg-primary-custom' : 'bg-success-custom'}">${item.test_type}</span></td> <td>${tickerOrUniverse}</td><td>${new Date(item.timestamp).toLocaleString()}</td><td>${matchCount}</td><td>${notesDisplay}</td> <td> <div class="btn-group"><a href="/?view_test_id=${item.id}" class="btn btn-sm btn-outline-primary-custom" title="View/Reload"><i class="bi bi-eye-fill"></i></a> <button class="btn btn-sm btn-outline-primary-custom share-btn" title="Share" data-id="${item.id}" data-uuid="${item.share_uuid || ''}"><i class="bi bi-share-fill"></i></button> <a href="/api/export_test/${item.id}" class="btn btn-sm btn-outline-primary-custom" title="Export"><i class="bi bi-download"></i></a></div> </td>`; tableBody.appendChild(row); }); }; const filterRows = () => { const searchTerm = document.getElementById('history-search').value.toLowerCase(); if (!searchTerm) { renderTable(allRowsData); return; } const filteredData = allRowsData.filter(item => { const params = item.parameters ? JSON.parse(item.parameters) : {}; let tickerOrUniverse = (item.test_type === 'Single') ? (params.ticker || '') : (params.universe || ''); return (item.test_name.toLowerCase().includes(searchTerm) || tickerOrUniverse.toLowerCase().includes(searchTerm) || (item.notes && item.notes.toLowerCase().includes(searchTerm))); }); renderTable(filteredData); }; renderTable(allRowsData); document.getElementById('history-search')?.addEventListener('input', filterRows); tableBody.addEventListener('click', handleShareClick); }).catch(error => { console.error('Failed to load history:', error); tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">Failed to load history: ${error.message}</td></tr>`; }); }
    async function handleShareClick (e) { const btn = e.target.closest('.share-btn'); if (!btn) return; const shareModal = new bootstrap.Modal(document.getElementById('shareModal')); const shareLinkInput = document.getElementById('shareLinkInput'); const testId = btn.dataset.id; const existingUuid = btn.dataset.uuid; btn.disabled = true; const originalIcon = btn.innerHTML; btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span>`; try { let shareUrl; if (existingUuid) { const url = new URL(window.location.href); shareUrl = `${url.protocol}//${url.host}/view/${existingUuid}`; } else { const response = await fetch(`/api/share_test/${testId}`, { method: 'POST' }); const data = await response.json(); if (data.share_url) { shareUrl = data.share_url; btn.dataset.uuid = data.share_url.split('/').pop(); } else { throw new Error("Could not generate share link."); } } shareLinkInput.value = shareUrl; shareModal.show(); } catch (error) { console.error('Sharing failed:', error); showAlert(error.message, 'danger'); } finally { btn.disabled = false; btn.innerHTML = originalIcon; } };
    
    initializeApp();
});