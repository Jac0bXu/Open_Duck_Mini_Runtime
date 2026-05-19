const socket = io();

// Connection history (localStorage)
function getSavedConnections() {
    try {
        return JSON.parse(localStorage.getItem('duck_connections') || '[]');
    } catch { return []; }
}

function saveConnection(hostname, username, port) {
    const connections = getSavedConnections();
    const entry = { hostname, username, port };
    // Remove duplicate by hostname
    const filtered = connections.filter(c => c.hostname !== hostname);
    filtered.unshift(entry);
    // Keep max 10
    localStorage.setItem('duck_connections', JSON.stringify(filtered.slice(0, 10)));
    renderConnectionList();
}

function renderConnectionList() {
    const datalist = document.getElementById('duck-list');
    datalist.innerHTML = '';
    getSavedConnections().forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.hostname;
        opt.label = c.username + '@' + c.hostname + ':' + c.port;
        datalist.appendChild(opt);
    });
}

// Fill form from saved data when hostname selected
document.getElementById('input-hostname').addEventListener('change', function() {
    const match = getSavedConnections().find(c => c.hostname === this.value);
    if (match) {
        document.getElementById('input-username').value = match.username;
        document.getElementById('input-port').value = match.port;
    }
});

renderConnectionList();

// Elements
const btnConnect = document.getElementById('btn-connect');
const btnDisconnect = document.getElementById('btn-disconnect');
const btnUpload = document.getElementById('btn-upload');
const btnCheckBt = document.getElementById('btn-check-bt');
const btnCheckVoltage = document.getElementById('btn-check-voltage');
const btnTurnOn = document.getElementById('btn-turn-on');
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnClearLog = document.getElementById('btn-clear-log');
const consoleLog = document.getElementById('console-log');
const uploadStatus = document.getElementById('upload-status');
const selectOnnx = document.getElementById('select-onnx');

// Badges
const badgeConn = document.getElementById('badge-connection');
const badgeWalk = document.getElementById('badge-walking');
const badgeCtrl = document.getElementById('badge-controller');
const badgeStream = document.getElementById('badge-streaming');

let btPollingInterval = null;

// Helpers
function setConnected(connected) {
    btnConnect.disabled = connected;
    btnDisconnect.disabled = !connected;
    btnUpload.disabled = !connected;
    btnCheckBt.disabled = !connected;
    btnCheckVoltage.disabled = !connected;
    btnTurnOn.disabled = !connected;
    btnStart.disabled = connected ? false : true;
    selectOnnx.disabled = !connected;
    badgeConn.textContent = connected ? 'Connected' : 'Disconnected';
    badgeConn.className = 'badge me-2 ' + (connected ? 'bg-success' : 'bg-secondary');

    if (connected) {
        startBtPolling();
        loadOnnxFiles();
    } else {
        stopBtPolling();
        setWalking(false);
        selectOnnx.innerHTML = '<option value="">Connect to load files...</option>';
    }
}

function setWalking(walking) {
    btnStart.disabled = walking;
    btnStop.disabled = !walking;
    selectOnnx.disabled = walking;
    badgeWalk.textContent = walking ? 'Walking' : 'Idle';
    badgeWalk.className = 'badge me-2 ' + (walking ? 'bg-success' : 'bg-secondary');
}

function appendLog(msg) {
    const line = document.createElement('div');
    line.textContent = msg;
    consoleLog.appendChild(line);
    consoleLog.scrollTop = consoleLog.scrollHeight;
    while (consoleLog.children.length > 500) {
        consoleLog.removeChild(consoleLog.firstChild);
    }
}

function loadOnnxFiles() {
    selectOnnx.innerHTML = '<option value="">Loading...</option>';
    fetch('/api/list-onnx')
        .then(r => r.json())
        .then(data => {
            selectOnnx.innerHTML = '';
            if (data.files.length === 0) {
                selectOnnx.innerHTML = '<option value="">No ONNX files found</option>';
                appendLog('No ONNX files found on robot');
            } else {
                selectOnnx.innerHTML = '<option value="">Select a policy...</option>';
                data.files.forEach(f => {
                    const opt = document.createElement('option');
                    opt.value = f;
                    // Show just filename as display text, full path as value
                    const name = f.split('/').pop();
                    const dir = f.substring(0, f.lastIndexOf('/'));
                    opt.textContent = name + '  (' + dir + ')';
                    selectOnnx.appendChild(opt);
                });
                appendLog('Found ' + data.files.length + ' ONNX file(s) on robot');
            }
        })
        .catch(() => {
            selectOnnx.innerHTML = '<option value="">Failed to load</option>';
        });
}

function startBtPolling() {
    stopBtPolling();
    btPollingInterval = setInterval(checkBluetooth, 3000);
    checkBluetooth();
}

function stopBtPolling() {
    if (btPollingInterval) {
        clearInterval(btPollingInterval);
        btPollingInterval = null;
    }
}

function checkBluetooth() {
    fetch('/api/bluetooth-status')
        .then(r => r.json())
        .then(data => {
            const count = data.controller_count;
            if (count >= 0) {
                badgeCtrl.textContent = 'Controller: ' + count;
                badgeCtrl.className = 'badge me-2 ' + (count > 0 ? 'bg-success' : 'bg-warning');
            } else {
                badgeCtrl.textContent = 'Controller: Error';
                badgeCtrl.className = 'badge me-2 bg-danger';
            }
        })
        .catch(() => {
            badgeCtrl.textContent = 'Controller: --';
            badgeCtrl.className = 'badge me-2 bg-secondary';
        });
}

// Connect
btnConnect.addEventListener('click', () => {
    const data = {
        hostname: document.getElementById('input-hostname').value.trim(),
        username: document.getElementById('input-username').value.trim() || 'pi',
        password: document.getElementById('input-password').value,
        port: parseInt(document.getElementById('input-port').value) || 22
    };
    if (!data.hostname) { alert('Please enter robot IP/hostname'); return; }

    btnConnect.disabled = true;
    btnConnect.textContent = 'Connecting...';
    fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(r => r.json())
    .then(data => {
        if (data.connected) {
            setConnected(true);
            if (data.walking) {
                setWalking(true);
                appendLog('Connected to ' + data.hostname + ' (walking already in progress)');
            } else {
                appendLog('Connected to ' + data.hostname);
            }
            saveConnection(
                document.getElementById('input-hostname').value.trim(),
                document.getElementById('input-username').value.trim(),
                document.getElementById('input-port').value
            );
        } else {
            setConnected(false);
            appendLog('Connection failed: ' + data.error);
        }
    })
    .catch(e => {
        setConnected(false);
        appendLog('Connection error: ' + e);
    })
    .finally(() => { btnConnect.textContent = 'Connect'; });
});

// Disconnect
btnDisconnect.addEventListener('click', () => {
    fetch('/api/disconnect', { method: 'POST' })
        .then(r => r.json())
        .then(() => {
            setConnected(false);
            appendLog('Disconnected');
        });
});

// Upload
btnUpload.addEventListener('click', () => {
    const fileInput = document.getElementById('input-policy-file');
    if (!fileInput.files.length) { alert('Please select an ONNX file'); return; }

    const formData = new FormData();
    formData.append('policy_file', fileInput.files[0]);

    btnUpload.disabled = true;
    btnUpload.textContent = 'Uploading...';
    uploadStatus.textContent = 'Uploading...';

    fetch('/api/upload-policy', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (data.uploaded) {
                uploadStatus.textContent = 'Uploaded to ' + data.remote_path;
                appendLog('Policy uploaded to ' + data.remote_path);
                loadOnnxFiles(); // Refresh the list
            } else {
                uploadStatus.textContent = 'Error: ' + data.error;
                appendLog('Upload failed: ' + data.error);
            }
        })
        .catch(e => {
            uploadStatus.textContent = 'Error: ' + e;
        })
        .finally(() => {
            btnUpload.disabled = false;
            btnUpload.textContent = 'Upload ONNX';
        });
});

// Check Bluetooth
btnCheckBt.addEventListener('click', checkBluetooth);

// Check Voltage
btnCheckVoltage.addEventListener('click', () => {
    btnCheckVoltage.disabled = true;
    btnCheckVoltage.textContent = 'Reading...';
    fetch('/api/check-voltage', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                appendLog('Voltage check failed: ' + data.error);
            }
        })
        .catch(e => appendLog('Voltage error: ' + e))
        .finally(() => {
            btnCheckVoltage.disabled = false;
            btnCheckVoltage.textContent = 'Check Voltage';
        });
});

// Turn On
btnTurnOn.addEventListener('click', () => {
    btnTurnOn.disabled = true;
    btnTurnOn.textContent = 'Turning on...';
    appendLog('Turning on robot...');

    fetch('/api/turn-on', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                appendLog('Robot turned on successfully');
            } else {
                appendLog('Turn on failed: ' + (data.error || data.output));
            }
        })
        .catch(e => appendLog('Error: ' + e))
        .finally(() => {
            btnTurnOn.disabled = false;
            btnTurnOn.textContent = 'Turn On';
        });
});

// Start Walk
btnStart.addEventListener('click', () => {
    const onnxPath = selectOnnx.value;
    if (!onnxPath) { alert('Please select an ONNX policy'); return; }

    const data = {
        onnx_path: onnxPath,
        action_scale: parseFloat(document.getElementById('input-action-scale').value),
        p: parseInt(document.getElementById('input-p').value),
        control_freq: parseInt(document.getElementById('input-freq').value),
        stream_data: document.getElementById('check-stream').checked,
        stream_port: 5678
    };

    fetch('/api/start-walk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(r => r.json())
    .then(result => {
        if (result.started) {
            setWalking(true);
            badgeStream.textContent = data.stream_data ? 'Stream: On' : 'Stream: Off';
            badgeStream.className = 'badge ' + (data.stream_data ? 'bg-success' : 'bg-secondary');
        } else {
            appendLog('Start failed: ' + result.error);
        }
    });
});

// Stop Walk
btnStop.addEventListener('click', () => {
    btnStop.disabled = true;
    fetch('/api/stop-walk', { method: 'POST' })
        .then(r => r.json())
        .then(() => {
            setWalking(false);
            badgeStream.textContent = 'Stream: Off';
            badgeStream.className = 'badge bg-secondary';
            appendLog('Walk stopped');
        });
});

// Clear Log
btnClearLog.addEventListener('click', () => {
    consoleLog.innerHTML = '';
});

// SocketIO events
socket.on('log_data', (data) => {
    appendLog(data.data);
});

socket.on('obs_data', (obs) => {
    updateCharts(obs);
});

socket.on('voltage_data', (data) => {
    updateVoltageChart(data.voltages);
});

socket.on('walk_status', (data) => {
    setWalking(data.walking);
});
