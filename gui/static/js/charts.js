const JOINT_NAMES = [
    "L Hip Yaw", "L Hip Roll", "L Hip Pitch", "L Knee", "L Ankle",
    "Neck P", "Head P", "Head Y", "Head R",
    "R Hip Yaw", "R Hip Roll", "R Hip Pitch", "R Knee", "R Ankle"
];

const MAX_POINTS = 100;

// Color palette for chart lines
const COLORS = [
    '#6ea8fe', '#ff6b6b', '#51cf66', '#ffd43b',
    '#cc5de8', '#ff922b', '#20c997', '#a9e34b',
    '#f06595', '#74c0fc', '#63e6be', '#e599f7',
    '#ffa94d', '#69db7c'
];

function makeChartConfig(labels, datasets) {
    return {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: {
                    display: datasets.length <= 4,
                    labels: { color: '#aaa', font: { size: 9 } }
                }
            },
            scales: {
                x: { display: false },
                y: {
                    ticks: { color: '#666', font: { size: 9 } },
                    grid: { color: '#333' }
                }
            },
            elements: {
                point: { radius: 0 },
                line: { borderWidth: 1.5 }
            }
        }
    };
}

function makeBarChartConfig(labels, colorFn) {
    return {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: new Array(labels.length).fill(0),
                backgroundColor: labels.map((_, i) => colorFn(i)),
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    ticks: { color: '#aaa', font: { size: 7 }, maxRotation: 45 },
                    grid: { display: false }
                },
                y: {
                    ticks: { color: '#666', font: { size: 9 } },
                    grid: { color: '#333' }
                }
            }
        }
    };
}

function makeRollingDatasets(count, names) {
    return names.map((name, i) => ({
        label: name,
        data: [],
        borderColor: COLORS[i % COLORS.length],
        backgroundColor: 'transparent',
        tension: 0.3,
        fill: false
    }));
}

// Joint positions bar chart
const jointChart = new Chart(
    document.getElementById('chart-joints'),
    makeBarChartConfig(JOINT_NAMES, i => COLORS[i % COLORS.length])
);

// Motor targets bar chart
const targetChart = new Chart(
    document.getElementById('chart-targets'),
    makeBarChartConfig(JOINT_NAMES, i => COLORS[i % COLORS.length])
);

// Gyro rolling line chart
const gyroDatasets = makeRollingDatasets(3, ['X', 'Y', 'Z']);
const gyroChart = new Chart(
    document.getElementById('chart-gyro'),
    makeChartConfig([], gyroDatasets)
);

// Accelerometer rolling line chart
const accelDatasets = makeRollingDatasets(3, ['X', 'Y', 'Z']);
const accelChart = new Chart(
    document.getElementById('chart-accel'),
    makeChartConfig([], accelDatasets)
);

function pushRolling(chart, datasets, values) {
    datasets.forEach((ds, i) => {
        ds.data.push(values[i]);
        if (ds.data.length > MAX_POINTS) ds.data.shift();
    });
    chart.data.labels = datasets[0].data.map((_, i) => i);
    chart.update();
}

function updateCharts(obs) {
    if (!obs) return;

    // Joint positions
    if (obs.dof_pos_relative) {
        jointChart.data.datasets[0].data = obs.dof_pos_relative;
        jointChart.update();
    }

    // Motor targets
    if (obs.motor_targets) {
        targetChart.data.datasets[0].data = obs.motor_targets;
        targetChart.update();
    }

    // IMU gyro
    if (obs.imu && obs.imu.gyro) {
        pushRolling(gyroChart, gyroDatasets, obs.imu.gyro);
    }

    // IMU accelero
    if (obs.imu && obs.imu.accelero) {
        pushRolling(accelChart, accelDatasets, obs.imu.accelero);
    }

    // Feet contacts
    if (obs.feet_contacts) {
        const left = document.getElementById('contact-left');
        const right = document.getElementById('contact-right');
        left.className = 'contact-indicator ' + (obs.feet_contacts[0] ? 'contact-on' : 'contact-off');
        right.className = 'contact-indicator ' + (obs.feet_contacts[1] ? 'contact-on' : 'contact-off');
    }

    // Commands
    if (obs.commands) {
        obs.commands.forEach((val, i) => {
            const el = document.getElementById('cmd-' + i);
            if (el) el.textContent = val.toFixed(3);
        });
    }
}
