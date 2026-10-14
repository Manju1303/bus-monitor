/* ==========================================================================
   Campus Transit Monitor - Frontend JavaScript Logic
   Mobile & Laptop Device Camera (WebRTC), CCTV Footage, KPI Polling & Real-Time Feed
   ========================================================================== */

let lastTopLogId = null;

// Client Device Camera State (Laptop Webcam / Mobile Camera)
let clientCameraStream = null;
let clientProcessInterval = null;
let isProcessingClientFrame = false;
let currentFacingMode = 'environment'; // 'environment' for rear mobile camera, 'user' for laptop webcam
let clientLoggedBanner = null;
let clientLoggedBannerTimer = 0;

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
        const plate = topLog['Registration Plate'] || 'Vehicle';
        const dir = topLog['Direction'] || 'Gate Event';
        showToast(`Bus ${plate} Recorded`, `Detected ${dir.toLowerCase()} and saved to gate records.`, 'success');
    }

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
 * Switch active video source programmatically & manage device camera
 */
async function switchVideoSource(selectedSource) {
    const sourceSelect = document.getElementById('video-source-select');
    const streamImg = document.getElementById('live-stream-feed');
    const pillDevice = document.getElementById('pill-device-cam');
    const pillSample = document.getElementById('pill-sample-cctv');
    const pillFlip = document.getElementById('pill-flip-cam');
    const badgeText = document.getElementById('camera-badge-text');

    if (sourceSelect) {
        sourceSelect.value = selectedSource;
    }

    // 1. Device Camera selected (Direct Mobile / Laptop Browser Webcam)
    if (selectedSource === 'device_camera') {
        if (pillDevice) pillDevice.classList.add('active');
        if (pillSample) pillSample.classList.remove('active');
        if (badgeText) badgeText.textContent = 'DEVICE CAMERA (LIVE)';
        await startDeviceCamera();
        return;
    }

    // 2. Switching to Server Source (CCTV footage, uploaded video, or server USB camera)
    stopDeviceCamera();

    if (pillDevice) pillDevice.classList.remove('active');
    if (pillFlip) pillFlip.style.display = 'none';
    if (pillSample) pillSample.classList.add('active');
    if (badgeText) badgeText.textContent = 'GATE CAM 01 (LIVE)';

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
            const sourceLabel = selectedSource === 'webcam' ? 'Server USB Webcam' : 'CCTV Video Footage';
            showToast('Feed Source Changed', `Streaming: ${sourceLabel}`, 'info');
        }
    } catch (err) {
        console.error('[STREAM] Error switching video source:', err);
        showToast('Feed Error', 'Failed to switch camera stream.', 'error');
    }
}

window.switchVideoSource = switchVideoSource;

/**
 * Connect and stream direct Laptop webcam or Mobile phone camera
 */
async function startDeviceCamera() {
    const video = document.getElementById('client-webcam-video');
    const canvas = document.getElementById('client-webcam-canvas');
    const streamImg = document.getElementById('live-stream-feed');
    const flipBtn = document.getElementById('pill-flip-cam');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showToast('Camera Notice', 'Browser camera access requires HTTPS or localhost. If opening from mobile, use HTTPS.', 'warning');
        return;
    }

    try {
        if (clientCameraStream) {
            clientCameraStream.getTracks().forEach(t => t.stop());
            clientCameraStream = null;
        }

        const constraints = {
            video: {
                facingMode: currentFacingMode,
                width: { ideal: 640 },
                height: { ideal: 480 }
            },
            audio: false
        };

        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        clientCameraStream = stream;

        if (video) {
            video.srcObject = stream;
            video.style.display = 'block';
            await video.play();
        }

        if (streamImg) streamImg.style.display = 'none';
        if (canvas) canvas.style.display = 'block';
        if (flipBtn) flipBtn.style.display = 'inline-flex';

        const camType = currentFacingMode === 'environment' ? 'Rear / Main Camera' : 'Front / Webcam';
        showToast('Device Camera Active', `Connected: ${camType}`, 'success');

        // Start real-time analysis loop (every 350ms)
        if (clientProcessInterval) clearInterval(clientProcessInterval);
        clientProcessInterval = setInterval(processClientVideoFrame, 350);
    } catch (err) {
        console.error('[DEVICE CAM] Error accessing camera:', err);
        showToast('Camera Permission Denied', err.message || 'Please allow camera permission in your browser.', 'error');
        // Fall back to sample footage
        switchVideoSource('default_footage');
    }
}

/**
 * Stop mobile / laptop camera stream and clear canvas
 */
function stopDeviceCamera() {
    if (clientCameraStream) {
        clientCameraStream.getTracks().forEach(t => t.stop());
        clientCameraStream = null;
    }
    if (clientProcessInterval) {
        clearInterval(clientProcessInterval);
        clientProcessInterval = null;
    }

    const video = document.getElementById('client-webcam-video');
    const canvas = document.getElementById('client-webcam-canvas');
    const streamImg = document.getElementById('live-stream-feed');
    const flipBtn = document.getElementById('pill-flip-cam');

    if (video) {
        video.pause();
        video.srcObject = null;
        video.style.display = 'none';
    }
    if (canvas) {
        canvas.style.display = 'none';
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    if (streamImg) streamImg.style.display = 'block';
    if (flipBtn) flipBtn.style.display = 'none';
}

/**
 * Flip between rear and front camera on mobile devices
 */
async function flipDeviceCamera() {
    currentFacingMode = (currentFacingMode === 'environment') ? 'user' : 'environment';
    await startDeviceCamera();
}

window.flipDeviceCamera = flipDeviceCamera;

/**
 * Send client camera frame to backend AI detector & draw bounding overlays
 */
async function processClientVideoFrame() {
    if (isProcessingClientFrame) return;

    const video = document.getElementById('client-webcam-video');
    const canvas = document.getElementById('client-webcam-canvas');
    if (!video || video.readyState < 2 || !canvas) return;

    isProcessingClientFrame = true;

    try {
        if (!window._offscreenCanvas) {
            window._offscreenCanvas = document.createElement('canvas');
            window._offscreenCanvas.width = 640;
            window._offscreenCanvas.height = 480;
        }
        const offCanvas = window._offscreenCanvas;
        const offCtx = offCanvas.getContext('2d');
        offCtx.drawImage(video, 0, 0, 640, 480);

        const dataUrl = offCanvas.toDataURL('image/jpeg', 0.65);

        const res = await fetch('/api/process_client_frame', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: dataUrl })
        });

        if (!res.ok) return;
        const data = await res.json();

        if (data.success) {
            // Check if vehicle line-crossing was logged
            if (data.logged_event) {
                clientLoggedBanner = data.logged_event;
                clientLoggedBannerTimer = 8;
                showToast(`Bus ${data.logged_event.plate} Recorded`, `Detected ${data.logged_event.direction} from camera and saved to database.`, 'success');

                const totalEl = document.getElementById('stat-total-records');
                if (totalEl) totalEl.textContent = parseInt(totalEl.textContent || '0') + 1;
                const logsRes = await fetch('/api/recent_logs');
                if (logsRes.ok) {
                    const logsData = await logsRes.json();
                    const activityList = document.getElementById('recent-activity-list');
                    if (activityList && logsData.logs) {
                        updateActivityFeed(logsData.logs, activityList);
                    }
                }
            }

            // Sync canvas resolution with display
            if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
                canvas.width = video.videoWidth || 640;
                canvas.height = video.videoHeight || 480;
            }

            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const scaleX = canvas.width / 640.0;
            const scaleY = canvas.height / 480.0;

            // Draw Gate Threshold Line
            const gateY = (data.gate_y || 240) * scaleY;
            ctx.strokeStyle = 'rgba(239, 68, 68, 0.9)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(0, gateY);
            ctx.lineTo(canvas.width, gateY);
            ctx.stroke();

            ctx.fillStyle = '#EF4444';
            ctx.font = 'bold 12px sans-serif';
            ctx.fillText('GATE THRESHOLD LINE', 15, gateY - 8);

            // Draw Detections & Plate Banners
            const detections = data.detections || [];
            detections.forEach(det => {
                const [x1, y1, x2, y2] = det.box;
                const sx1 = x1 * scaleX;
                const sy1 = y1 * scaleY;
                const sx2 = x2 * scaleX;
                const sy2 = y2 * scaleY;
                const w = sx2 - sx1;
                const h = sy2 - sy1;

                // Vehicle Bounding Box
                ctx.strokeStyle = '#10B981';
                ctx.lineWidth = 2.5;
                ctx.strokeRect(sx1, sy1, w, h);

                // Label Badge
                const labelText = `${det.label} (${Math.round(det.confidence * 100)}%)`;
                ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
                ctx.fillRect(sx1, Math.max(0, sy1 - 22), 120, 20);
                ctx.fillStyle = '#10B981';
                ctx.font = 'bold 11px sans-serif';
                ctx.fillText(labelText, sx1 + 6, Math.max(0, sy1 - 8));

                // Plate Box
                if (det.plate && det.plate !== 'READING...') {
                    const plateText = `PLATE: ${det.plate}`;
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.9)';
                    ctx.fillRect(sx1, sy2 + 4, 160, 24);
                    ctx.fillStyle = '#FACC15';
                    ctx.font = 'bold 13px monospace';
                    ctx.fillText(plateText, sx1 + 8, sy2 + 20);
                }
            });

            // Draw On-Screen Logged Event Banner if active
            if (clientLoggedBannerTimer > 0) {
                clientLoggedBannerTimer--;
                ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
                ctx.fillRect(15, 12, canvas.width - 30, 46);
                ctx.strokeStyle = '#10B981';
                ctx.lineWidth = 2;
                ctx.strokeRect(15, 12, canvas.width - 30, 46);

                ctx.fillStyle = '#FFFFFF';
                ctx.font = 'bold 15px sans-serif';
                ctx.fillText(`LOGGED ${clientLoggedBanner.direction.toUpperCase()}: ${clientLoggedBanner.plate} [EVIDENCE SAVED]`, 28, 40);
            }
        }
    } catch (err) {
        console.warn('[FRAME PROCESS] Frame error:', err);
    } finally {
        isProcessingClientFrame = false;
    }
}

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

                stopDeviceCamera();

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

                const pillDevice = document.getElementById('pill-device-cam');
                const pillSample = document.getElementById('pill-sample-cctv');
                if (pillDevice) pillDevice.classList.remove('active');
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
