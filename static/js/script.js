/* ==========================================================================
   Campus Transit Monitor - Frontend JavaScript Logic
   Drag & Drop Video Upload, Live Stream Controls, KPI Polling, Real-Time Activity Feed & PWA
   ========================================================================== */

let lastTopLogId = null;

document.addEventListener('DOMContentLoaded', () => {
    initServiceWorker();
    initRealtimePolling();
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
 * Poll KPI metrics and real-time gate activity logs every 2.5 seconds
 */
function initRealtimePolling() {
    const totalEl = document.getElementById('stat-total-records');
    const campusEl = document.getElementById('stat-on-campus');
    const exitedEl = document.getElementById('stat-exited-today');
    const statusEl = document.getElementById('stat-model-status');
    const activityList = document.getElementById('recent-activity-list');

    async function fetchStatsAndLogs() {
        try {
            const [statsRes, logsRes] = await Promise.all([
                fetch('/api/stats'),
                fetch('/api/recent_logs')
            ]);

            if (statsRes.ok) {
                const stats = await statsRes.json();
                if (totalEl) totalEl.textContent = stats.total_records || 0;
                if (campusEl) campusEl.textContent = stats.on_campus || 0;
                if (exitedEl) exitedEl.textContent = stats.exited_today || 0;
                if (statusEl) statusEl.textContent = stats.model_status || 'Operational';
            }

            if (logsRes.ok && activityList) {
                const logsData = await logsRes.json();
                if (logsData.success && Array.isArray(logsData.logs) && logsData.logs.length > 0) {
                    updateActivityFeed(logsData.logs, activityList);
                }
            }
        } catch (err) {
            console.warn('[POLL] Real-time poll warning:', err);
        }
    }

    fetchStatsAndLogs();
    setInterval(fetchStatsAndLogs, 2500);
}

/**
 * Dynamically re-render the recent activity feed when new logs arrive
 */
function updateActivityFeed(logs, container) {
    const topLog = logs[0];
    const topId = topLog['Log ID'];

    if (lastTopLogId !== null && topId !== lastTopLogId) {
        // New bus event detected!
        const plate = topLog['Registration Plate'] || 'Vehicle';
        const dir = topLog['Direction'] || 'Gate Event';
        showToast(`Bus ${plate} Recorded`, `Detected ${dir.toLowerCase()} & saved to gate records.`, 'success');
    }

    // Only rebuild DOM if top ID changed or container was empty
    if (topId !== lastTopLogId) {
        lastTopLogId = topId;

        container.innerHTML = logs.map(log => {
            const isCampus = log['Status'] === 'ON CAMPUS';
            const badgeClass = isCampus ? 'badge-campus' : 'badge-exited';
            const iconClass = isCampus ? 'entry' : 'exit';
            const timeDisplay = (log['Entry Time'] && log['Entry Time'] !== '-') ? log['Entry Time'] : log['Exit Time'];
            const durationText = (!isCampus && log['Duration (Minutes)'] && log['Duration (Minutes)'] !== '-') 
                ? ` (${log['Duration (Minutes)']}m)` : '';

            const photoHtml = log['Snapshot'] ? `
                <a href="/static/snapshots/${log['Snapshot']}" target="_blank" class="btn-snapshot" title="View captured camera evidence">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/>
                        <circle cx="12" cy="13" r="3"/>
                    </svg>
                    <span>Photo</span>
                </a>
            ` : '';

            const iconSvg = isCampus ? `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"/>
                    <polyline points="19 12 12 19 5 12"/>
                </svg>
            ` : `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="19" x2="12" y2="5"/>
                    <polyline points="5 12 12 5 19 12"/>
                </svg>
            `;

            return `
                <li class="activity-item">
                    <div class="activity-main">
                        <div class="activity-icon-badge ${iconClass}">
                            ${iconSvg}
                        </div>
                        <div class="activity-details">
                            <span class="plate-badge">${log['Registration Plate']}</span>
                            <span class="activity-meta">${timeDisplay}</span>
                        </div>
                    </div>
                    <div class="activity-tags">
                        ${photoHtml}
                        <span class="badge ${badgeClass}">${log['Status']}${durationText}</span>
                    </div>
                </li>
            `;
        }).join('');
    }
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
 * Switch active video feed source (dropdown handler)
 */
function initStreamControls() {
    const sourceSelect = document.getElementById('video-source-select');
    if (!sourceSelect) return;

    sourceSelect.addEventListener('change', (e) => {
        switchVideoSource(e.target.value);
    });
}

/**
 * Switch active video source programmatically & update UI pills
 */
async function switchVideoSource(selectedSource) {
    const sourceSelect = document.getElementById('video-source-select');
    const streamImg = document.getElementById('live-stream-feed');
    const pillLive = document.getElementById('pill-live-cam');
    const pillSample = document.getElementById('pill-sample-cctv');
    const badgeText = document.getElementById('camera-badge-text');

    // Update active pill classes
    if (pillLive && pillSample) {
        if (selectedSource === 'webcam') {
            pillLive.classList.add('active');
            pillSample.classList.remove('active');
            if (badgeText) badgeText.textContent = 'LIVE WEBCAM • ACTIVE';
        } else {
            pillLive.classList.remove('active');
            pillSample.classList.add('active');
            if (badgeText) badgeText.textContent = 'GATE CAM 01 • LIVE';
        }
    }

    if (sourceSelect) {
        sourceSelect.value = selectedSource;
    }

    try {
        const res = await fetch('/api/set_source', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: selectedSource })
        });
        const data = await res.json();
        if (data.success && streamImg) {
            const currentSrc = streamImg.src.split('?')[0];
            streamImg.src = currentSrc + '?t=' + new Date().getTime();
            const sourceLabel = selectedSource === 'webcam' ? 'Live Webcam' : 'CCTV Video Footage';
            showToast('Feed Source Changed', `Now streaming: ${sourceLabel}`, 'info');
        }
    } catch (err) {
        console.error('[STREAM] Error switching video source:', err);
        showToast('Feed Error', 'Failed to switch camera stream.', 'error');
    }
}

window.switchVideoSource = switchVideoSource;

/**
 * Manually snapshot & record vehicle currently visible in camera stream
 */
async function triggerManualCapture() {
    const btn = document.getElementById('btn-manual-capture');
    if (btn) {
        btn.disabled = true;
        btn.classList.add('loading');
    }

    try {
        const res = await fetch('/api/capture_now', { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            showToast('Vehicle Recorded!', `${data.message} - Added to gate log`, 'success');
            // Refresh counts & feed immediately
            const totalEl = document.getElementById('stat-total-records');
            if (totalEl) totalEl.textContent = parseInt(totalEl.textContent || '0') + 1;
            const resLogs = await fetch('/api/recent_logs');
            if (resLogs.ok) {
                const logsData = await resLogs.json();
                const activityList = document.getElementById('recent-activity-list');
                if (activityList && logsData.logs) {
                    updateActivityFeed(logsData.logs, activityList);
                }
            }
        } else {
            showToast('Capture Notice', data.error || 'No vehicle found in view to capture.', 'warning');
        }
    } catch (err) {
        console.error('[CAPTURE] Manual capture error:', err);
        showToast('Capture Failed', 'Communication error with gate camera server.', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('loading');
        }
    }
}

window.triggerManualCapture = triggerManualCapture;

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

    dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });

    async function handleFileUpload(file) {
        if (!file) return;

        showStatus('Uploading & analyzing video: ' + file.name + '...', 'info');

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
                showToast('Video Loaded', `Processing CCTV footage: ${data.filename}`, 'success');

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

                if (streamImg) {
                    const currentSrc = streamImg.src.split('?')[0];
                    streamImg.src = currentSrc + '?t=' + new Date().getTime();
                }

                // Uncheck live webcam pill
                const pillLive = document.getElementById('pill-live-cam');
                const pillSample = document.getElementById('pill-sample-cctv');
                if (pillLive) pillLive.classList.remove('active');
                if (pillSample) pillSample.classList.remove('active');
            } else {
                showStatus('Upload Failed: ' + (data.error || 'Invalid file format'), 'error');
                showToast('Upload Error', data.error || 'Failed to upload video', 'error');
            }
        } catch (err) {
            console.error('[UPLOAD] Exception uploading video:', err);
            showStatus('Upload failed. Please check network connection.', 'error');
            showToast('Upload Error', 'Failed to send video file to server.', 'error');
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

/**
 * Display modern floating toast notifications
 */
function showToast(title, message, type = 'info') {
    const container = document.getElementById('live-toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `live-toast ${type}`;

    let iconSvg = '';
    if (type === 'success') {
        iconSvg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
    } else if (type === 'error') {
        iconSvg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
    } else if (type === 'warning') {
        iconSvg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
    } else {
        iconSvg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
    }

    toast.innerHTML = `
        <div class="toast-icon">${iconSvg}</div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

window.showToast = showToast;

/**
 * Auto-recovery stream reconnection handler
 */
function handleStreamError(img) {
    if (!img) return;
    console.warn('[STREAM] Video feed interrupted. Attempting reconnect in 2s...');
    setTimeout(() => {
        const baseSrc = img.src.split('?')[0];
        img.src = baseSrc + '?t=' + Date.now();
    }, 2000);
}

window.handleStreamError = handleStreamError;

/**
 * Seed or refresh sample gate activity logs
 */
async function populateSampleRecords() {
    try {
        const res = await fetch('/api/seed_samples', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('Sample Data Seeded', 'Sample campus records generated across shifts.', 'success');
            setTimeout(() => window.location.reload(), 1000);
        }
    } catch (err) {
        console.error('[SAMPLE] Error seeding sample records:', err);
    }
}

window.populateSampleRecords = populateSampleRecords;
