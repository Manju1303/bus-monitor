/* ==========================================================================
   Campus Transit Monitor - Frontend JavaScript Logic
   Drag & Drop Video Upload, Live Stream Controls, KPI Polling, Records Search & PWA
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    initServiceWorker();
    initStatsPolling();
    initRecordsFiltering();
    initStreamControls();
    initVideoUpload();
});

/**
 * Register Progressive Web App (PWA) Service Worker
 */
function initServiceWorker() {
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js')
                .then(reg => {
                    console.log('[PWA] Service Worker registered successfully:', reg.scope);
                })
                .catch(err => {
                    console.warn('[PWA] Service Worker registration failed:', err);
                });
        });
    }
}

/**
 * Poll KPI metrics every 3 seconds to update dashboard status numbers
 */
function initStatsPolling() {
    const totalEl = document.getElementById('stat-total-records');
    const campusEl = document.getElementById('stat-on-campus');
    const exitedEl = document.getElementById('stat-exited-today');
    const statusEl = document.getElementById('stat-model-status');

    if (!totalEl) return;

    async function fetchStats() {
        try {
            const res = await fetch('/api/stats');
            if (!res.ok) return;
            const data = await res.json();

            if (totalEl) totalEl.textContent = data.total_records || 0;
            if (campusEl) campusEl.textContent = data.on_campus || 0;
            if (exitedEl) exitedEl.textContent = data.exited_today || 0;
            if (statusEl) statusEl.textContent = data.model_status || 'Operational';
        } catch (err) {
            console.warn('[STATS] Stats poll warning:', err);
        }
    }

    fetchStats();
    setInterval(fetchStats, 3000);
}

/**
 * Filter records table based on search input & status dropdown
 */
function initRecordsFiltering() {
    const searchInput = document.getElementById('record-search');
    const statusSelect = document.getElementById('record-status-filter');
    const tableRows = document.querySelectorAll('#records-table tbody tr');

    if (!searchInput && !statusSelect) return;

    function filterTable() {
        const query = searchInput ? searchInput.value.toLowerCase().trim() : '';
        const status = statusSelect ? statusSelect.value.toUpperCase() : 'ALL';

        tableRows.forEach(row => {
            const plate = row.getAttribute('data-plate') || '';
            const vehId = row.getAttribute('data-id') || '';
            const rowStatus = row.getAttribute('data-status') || '';
            const direction = row.getAttribute('data-direction') || '';

            const matchesQuery = !query || 
                plate.toLowerCase().includes(query) || 
                vehId.toLowerCase().includes(query) || 
                direction.toLowerCase().includes(query);

            const matchesStatus = (status === 'ALL') || (rowStatus.toUpperCase() === status);

            row.style.display = (matchesQuery && matchesStatus) ? '' : 'none';
        });
    }

    if (searchInput) searchInput.addEventListener('input', filterTable);
    if (statusSelect) statusSelect.addEventListener('change', filterTable);
}

/**
 * Switch active video feed source from dropdown
 */
function initStreamControls() {
    const sourceSelect = document.getElementById('video-source-select');
    const streamImg = document.getElementById('live-stream-feed');

    if (!sourceSelect) return;

    sourceSelect.addEventListener('change', async (e) => {
        const selectedSource = e.target.value;
        try {
            const res = await fetch('/api/set_source', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source: selectedSource })
            });
            const data = await res.json();
            if (data.success && streamImg) {
                // Refresh image feed URL with timestamp query param
                const currentSrc = streamImg.src.split('?')[0];
                streamImg.src = currentSrc + '?t=' + new Date().getTime();
            }
        } catch (err) {
            console.error('[STREAM] Error switching video source:', err);
        }
    });
}

/**
 * Handle Drag & Drop and File Explorer Video Uploads
 */
function initVideoUpload() {
    const dropzone = document.getElementById('upload-dropzone');
    const fileInput = document.getElementById('video-upload-input');
    const sourceSelect = document.getElementById('video-source-select');
    const streamImg = document.getElementById('live-stream-feed');
    const statusMsg = document.getElementById('upload-status-msg');

    if (!dropzone || !fileInput) return;

    // Highlight dropzone on drag over
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dragover');
        }, false);
    });

    // Handle dropped file
    dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    // Handle file selected from file dialog
    fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });

    /**
     * Upload video file via fetch API
     */
    async function handleFileUpload(file) {
        if (!file) return;

        showStatus('Uploading video file: ' + file.name + '...', 'info');

        const formData = new FormData();
        formData.append('video', file);

        try {
            const res = await fetch('/api/upload_video', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (data.success) {
                showStatus('Uploaded & Active: ' + data.filename, 'success');

                // Check if option exists in dropdown, else add it
                if (sourceSelect) {
                    let optExists = Array.from(sourceSelect.options).some(opt => opt.value === data.path);
                    if (!optExists) {
                        const newOption = document.createElement('option');
                        newOption.value = data.path;
                        newOption.textContent = `Uploaded: ${data.filename}`;
                        sourceSelect.appendChild(newOption);
                    }
                    sourceSelect.value = data.path;
                }

                // Force refresh live stream img feed
                if (streamImg) {
                    const currentSrc = streamImg.src.split('?')[0];
                    streamImg.src = currentSrc + '?t=' + new Date().getTime();
                }
            } else {
                showStatus('Upload Failed: ' + (data.error || 'Invalid file format'), 'error');
            }
        } catch (err) {
            console.error('[UPLOAD] Exception uploading video:', err);
            showStatus('Upload failed. Please try again.', 'error');
        } finally {
            fileInput.value = '';
        }
    }

    function showStatus(message, type) {
        if (!statusMsg) return;
        statusMsg.textContent = message;
        statusMsg.className = `upload-status ${type}`;
        statusMsg.style.display = 'block';
    }
}
