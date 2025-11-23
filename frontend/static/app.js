/**
 * Easy BDD Framework - Modern Frontend Application
 * Main JavaScript file for the web interface
 */

class EasyBDDApp {
    constructor() {
        this.API_BASE = '/api';
        this.currentTestFile = null;
        this.monaco = null;
        this.activeTab = 'tests';
        this.testResults = [];
        this.runningTests = new Map();
        this.charts = {};
        
        this.init();
    }

    setupErrorMonitoring() {
        // Global error handler for Chart.js issues
        window.addEventListener('error', (event) => {
            if (event.error && event.error.message && event.error.message.includes('Chart')) {
                console.warn('Chart.js error caught:', event.error.message);
                this.showNotification('Chart display temporarily unavailable', 'warning');
                event.preventDefault(); // Prevent the error from bubbling up
            }
        });

        // Unhandled promise rejection handler
        window.addEventListener('unhandledrejection', (event) => {
            if (event.reason && event.reason.toString().includes('Chart')) {
                console.warn('Chart.js promise rejection:', event.reason);
                this.showNotification('Chart functionality temporarily disabled', 'warning');
                event.preventDefault();
            }
        });
    }

    async init() {
        this.setupErrorMonitoring();
        this.setupEventListeners();
        this.setupTabNavigation();
        this.setupDarkMode();
        await this.initializeMonacoEditor();
        await this.loadInitialData();
    }

    setupEventListeners() {
        // Navigation buttons
        document.getElementById('refreshTestsBtn')?.addEventListener('click', () => this.loadTests());
        document.getElementById('uploadTestBtn')?.addEventListener('click', () => this.showUploadModal());
        document.getElementById('newTestBtn')?.addEventListener('click', () => this.createNewTest());
        document.getElementById('saveTestBtn')?.addEventListener('click', () => this.saveCurrentTest());
        document.getElementById('refreshScreenshotsBtn')?.addEventListener('click', () => this.loadScreenshots());
        document.getElementById('saveConfigBtn')?.addEventListener('click', () => this.saveConfig());
        document.getElementById('exportResultsBtn')?.addEventListener('click', () => this.exportResults());

        // Modal events
        document.getElementById('confirmUploadBtn')?.addEventListener('click', () => this.uploadFile());
        document.getElementById('cancelUploadBtn')?.addEventListener('click', () => this.hideUploadModal());
        document.getElementById('confirmRunBtn')?.addEventListener('click', () => this.runSelectedTest());
        document.getElementById('cancelRunBtn')?.addEventListener('click', () => this.hideRunModal());
        document.getElementById('cancelTestBtn')?.addEventListener('click', () => this.cancelRunningTest());

        // Search and filter
        document.getElementById('testSearch')?.addEventListener('input', (e) => this.filterTests(e.target.value));
        document.getElementById('tagFilter')?.addEventListener('change', (e) => this.filterByTag(e.target.value));

        // Dark mode toggle
        document.getElementById('darkModeToggle')?.addEventListener('click', () => this.toggleDarkMode());
    }

    setupTabNavigation() {
        const tabs = document.querySelectorAll('.tab-btn');
        const contents = document.querySelectorAll('.tab-content');

        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const targetTab = tab.id.replace('Tab', '');
                
                // Update tab states
                tabs.forEach(t => {
                    t.classList.remove('active', 'border-primary-500', 'text-primary-600');
                    t.classList.add('border-transparent', 'text-gray-500');
                });
                
                tab.classList.add('active', 'border-primary-500', 'text-primary-600');
                tab.classList.remove('border-transparent', 'text-gray-500');

                // Show/hide content
                contents.forEach(content => content.classList.add('hidden'));
                const targetContent = document.getElementById(`${targetTab}Content`);
                if (targetContent) {
                    targetContent.classList.remove('hidden');
                }

                this.activeTab = targetTab;
                this.onTabChange(targetTab);
            });
        });
    }

    setupDarkMode() {
        const savedMode = localStorage.getItem('darkMode');
        if (savedMode === 'true' || (!savedMode && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
            this.updateDarkModeIcon(true);
        }
    }

    toggleDarkMode() {
        const isDark = document.documentElement.classList.toggle('dark');
        localStorage.setItem('darkMode', isDark.toString());
        this.updateDarkModeIcon(isDark);
    }

    updateDarkModeIcon(isDark) {
        const icon = document.querySelector('#darkModeToggle i');
        if (icon) {
            icon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
        }
    }

    async initializeMonacoEditor() {
        return new Promise((resolve) => {
            require.config({ paths: { vs: 'https://unpkg.com/monaco-editor@0.44.0/min/vs' } });
            require(['vs/editor/editor.main'], () => {
                monaco.languages.register({ id: 'yaml' });
                
                this.monaco = monaco.editor.create(document.getElementById('monacoEditor'), {
                    value: this.getDefaultTestTemplate(),
                    language: 'yaml',
                    theme: document.documentElement.classList.contains('dark') ? 'vs-dark' : 'vs-light',
                    automaticLayout: true,
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                    lineNumbers: 'on',
                    folding: true,
                    fontSize: 14
                });

                // Watch for dark mode changes
                const observer = new MutationObserver(() => {
                    const isDark = document.documentElement.classList.contains('dark');
                    monaco.editor.setTheme(isDark ? 'vs-dark' : 'vs-light');
                });
                observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

                resolve();
            });
        });
    }

    async loadInitialData() {
        await Promise.all([
            this.loadTests(),
            this.loadSystemInfo(),
            this.loadConfig(),
            this.loadResults(),
            this.loadScreenshots()
        ]);
        this.updateDashboardStats();
    }

    async loadTests() {
        try {
            const response = await fetch(`${this.API_BASE}/tests/list`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const data = await response.json();
            
            this.renderTestsList(data.tests);
            this.updateTagFilter(data.tests);
            this.updateDashboardStats({ totalTests: data.total });
        } catch (error) {
            this.showNotification('Error loading tests: ' + error.message, 'error');
        }
    }

    renderTestsList(tests) {
        const container = document.getElementById('testsList');
        if (!container) return;

        if (tests.length === 0) {
            container.innerHTML = `
                <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                    <i class="fas fa-file-code text-4xl mb-4"></i>
                    <p>No test files found</p>
                    <button class="mt-4 bg-primary-500 text-white px-4 py-2 rounded-lg hover:bg-primary-600 transition-colors"
                            onclick="document.getElementById('uploadTestBtn').click()">
                        <i class="fas fa-plus mr-2"></i>Add Your First Test
                    </button>
                </div>
            `;
            return;
        }

        container.innerHTML = tests.map(test => {
            // Ensure tags and description are arrays/strings
            const tags = Array.isArray(test.tags) ? test.tags : [];
            const description = test.description || 'No description';
            
            return `
            <div class="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition-shadow test-item"
                 data-tags="${tags.join(',')}" data-name="${test.name.toLowerCase()}">
                <div class="flex items-center justify-between">
                    <div class="flex-1">
                        <div class="flex items-center space-x-3">
                            <h4 class="text-lg font-medium text-gray-900 dark:text-white">${test.name}</h4>
                            ${test.error ? '<i class="fas fa-exclamation-triangle text-red-500"></i>' : ''}
                        </div>
                        <p class="text-gray-600 dark:text-gray-400 mt-1">${description}</p>
                        <div class="flex items-center space-x-4 mt-2 text-sm text-gray-500 dark:text-gray-400">
                            <span><i class="fas fa-calendar mr-1"></i>${new Date(test.modified).toLocaleDateString()}</span>
                            <span><i class="fas fa-file mr-1"></i>${(test.size / 1024).toFixed(1)} KB</span>
                            ${tags.length > 0 ? `<span><i class="fas fa-tags mr-1"></i>${tags.join(', ')}</span>` : ''}
                        </div>
                    </div>
                    <div class="flex items-center space-x-2">
                        <button class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg transition-colors"
                                onclick="app.editTest('${test.name}')">
                            <i class="fas fa-edit mr-2"></i>Edit
                        </button>
                        <button class="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-lg transition-colors"
                                onclick="app.showRunModal('${test.name}')">
                            <i class="fas fa-play mr-2"></i>Run
                        </button>
                    </div>
                </div>
            </div>`;
        }).join('');
    }

    updateTagFilter(tests) {
        const tagFilter = document.getElementById('tagFilter');
        if (!tagFilter) return;

        // Extract all unique tags, ensuring we handle undefined tags
        const allTags = [...new Set(tests.flatMap(test => 
            Array.isArray(test.tags) ? test.tags : []
        ))].filter(tag => tag && tag.trim()).sort();
        
        tagFilter.innerHTML = '<option value="">All Tags</option>' + 
            allTags.map(tag => `<option value="${tag}">${tag}</option>`).join('');
    }

    filterTests(searchTerm) {
        const items = document.querySelectorAll('.test-item');
        const term = searchTerm.toLowerCase();

        items.forEach(item => {
            const name = item.dataset.name;
            const visible = name.includes(term);
            item.style.display = visible ? 'block' : 'none';
        });
    }

    filterByTag(tag) {
        const items = document.querySelectorAll('.test-item');

        items.forEach(item => {
            const tags = item.dataset.tags;
            const visible = !tag || tags.includes(tag);
            item.style.display = visible ? 'block' : 'none';
        });
    }

    async editTest(testPath) {
        try {
            const response = await fetch(`${this.API_BASE}/tests/${testPath}`);
            const data = await response.json();
            
            this.currentTestFile = data;
            this.monaco.setValue(data.content);
            this.updateCurrentFileInfo(data);
            this.switchToTab('editor');
        } catch (error) {
            this.showNotification('Error loading test file: ' + error.message, 'error');
        }
    }

    switchToTab(tabName) {
        document.getElementById(`${tabName}Tab`).click();
    }

    updateCurrentFileInfo(fileData) {
        const info = document.getElementById('currentFileInfo');
        if (!info) return;

        info.innerHTML = `
            <div class="space-y-2">
                <div><strong>File:</strong> ${fileData.path}</div>
                <div><strong>Size:</strong> ${this.formatFileSize(fileData.size)}</div>
                <div><strong>Modified:</strong> ${new Date(fileData.modified).toLocaleString()}</div>
            </div>
        `;
    }

    async saveCurrentTest() {
        if (!this.currentTestFile) {
            this.showNotification('No file selected', 'error');
            return;
        }

        try {
            const content = this.monaco.getValue();
            const response = await fetch(`${this.API_BASE}/tests/${this.currentTestFile.path}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: this.currentTestFile.path.split('/').pop(),
                    description: 'Updated via web interface',
                    content: content
                })
            });

            if (response.ok) {
                this.showNotification('Test file saved successfully', 'success');
                await this.loadTests(); // Refresh tests list
            } else {
                throw new Error('Failed to save file');
            }
        } catch (error) {
            this.showNotification('Error saving test file: ' + error.message, 'error');
        }
    }

    createNewTest() {
        this.currentTestFile = {
            path: 'tests/cases/new_test.yaml',
            content: this.getDefaultTestTemplate()
        };
        
        this.monaco.setValue(this.currentTestFile.content);
        this.updateCurrentFileInfo({
            path: 'new_test.yaml',
            size: this.currentTestFile.content.length,
            modified: new Date().toISOString()
        });
        
        this.switchToTab('editor');
    }

    getDefaultTestTemplate() {
        return `name: "New Test"
description: "A new test created via the web interface"
tags: ["new", "web-created"]

variables:
  app_url: "https://example.com"
  username: "testuser"
  password: "testpass"

steps:
  - action: Open browser
    url: \${app_url}
    description: "Open the application homepage"
    
  - action: Take screenshot
    name: "homepage"
    description: "Capture initial state"
    
  - action: Verify text
    text: "Welcome"
    description: "Verify welcome message appears"
`;
    }

    showRunModal(testPath) {
        document.getElementById('testFileToRun').value = testPath;
        document.getElementById('runTestModal').classList.remove('hidden');
        document.getElementById('runTestModal').classList.add('flex');
    }

    hideRunModal() {
        document.getElementById('runTestModal').classList.add('hidden');
        document.getElementById('runTestModal').classList.remove('flex');
    }

    async runSelectedTest() {
        const testPath = document.getElementById('testFileToRun').value;
        const tags = document.getElementById('testTags').value
            .split(',')
            .map(tag => tag.trim())
            .filter(tag => tag.length > 0);
        const headless = document.getElementById('runHeadless').checked;
        const exportFormat = document.getElementById('exportFormat').value;

        this.hideRunModal();
        this.showProgressModal();

        try {
            const response = await fetch(`${this.API_BASE}/tests/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    test_path: testPath,
                    tags: tags.length > 0 ? tags : null,
                    headless: headless,
                    export_format: exportFormat || null
                })
            });

            const data = await response.json();
            this.monitorTestExecution(data.test_id);
        } catch (error) {
            this.hideProgressModal();
            this.showNotification('Error starting test: ' + error.message, 'error');
        }
    }

    showProgressModal() {
        document.getElementById('progressModal').classList.remove('hidden');
        document.getElementById('progressModal').classList.add('flex');
    }

    hideProgressModal() {
        document.getElementById('progressModal').classList.add('hidden');
        document.getElementById('progressModal').classList.remove('flex');
    }

    async monitorTestExecution(testId) {
        const progressBar = document.getElementById('progressBar');
        const progressPercent = document.getElementById('progressPercent');
        const progressStatus = document.getElementById('progressStatus');

        const checkProgress = async () => {
            try {
                const response = await fetch(`${this.API_BASE}/tests/status/${testId}`);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const data = await response.json();

                // Safe progress handling
                const progress = data.progress || 0;
                const status = data.status || 'unknown';
                const currentStep = data.current_step || data.output || 'Processing...';

                progressBar.style.width = `${progress}%`;
                progressPercent.textContent = `${progress}%`;
                progressStatus.textContent = currentStep;

                if (status === 'completed' || status === 'failed') {
                    this.hideProgressModal();
                    
                    try {
                        await this.loadResults();
                        this.updateDashboardStats();
                    } catch (chartError) {
                        console.warn('Chart update failed after test completion:', chartError);
                        // Still proceed with notification even if charts fail
                    }
                    
                    const message = status === 'completed' ? 
                        'Test completed successfully!' : 
                        'Test failed: ' + (data.error || 'Unknown error');
                    
                    this.showNotification(message, status === 'completed' ? 'success' : 'error');
                    return;
                }

                setTimeout(checkProgress, 1000);
            } catch (error) {
                this.hideProgressModal();
                this.showNotification('Error monitoring test: ' + error.message, 'error');
            }
        };

        checkProgress();
    }

    async loadResults() {
        try {
            const response = await fetch(`${this.API_BASE}/tests/results`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const data = await response.json();
            
            if (data && Array.isArray(data.results)) {
                this.testResults = data.results;
                this.renderResultsList(data.results);
                this.updateResultsCharts(data.results);
            } else {
                this.testResults = [];
                this.renderResultsList([]);
                this.updateResultsCharts([]);
            }
        } catch (error) {
            console.warn('Test results not available:', error.message);
            this.testResults = [];
            this.renderResultsList([]);
            this.updateResultsCharts([]);
        }
    }

    renderResultsList(results) {
        const container = document.getElementById('resultsList');
        if (!container) return;

        if (results.length === 0) {
            container.innerHTML = `
                <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                    <i class="fas fa-chart-line text-4xl mb-4"></i>
                    <p>No test results yet</p>
                    <p class="text-sm">Run some tests to see results here</p>
                </div>
            `;
            return;
        }

        container.innerHTML = results
            .sort((a, b) => new Date(b.completed) - new Date(a.completed))
            .slice(0, 20) // Show only last 20 results
            .map(result => `
                <div class="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                    <div class="flex items-center justify-between">
                        <div class="flex-1">
                            <div class="flex items-center space-x-3">
                                <h4 class="text-lg font-medium text-gray-900 dark:text-white">Test ${result.test_id}</h4>
                                <span class="px-2 py-1 text-xs rounded-full ${this.getStatusBadgeClass(result.status)}">
                                    ${result.status.toUpperCase()}
                                </span>
                            </div>
                            <div class="mt-2 text-sm text-gray-600 dark:text-gray-400">
                                <span><i class="fas fa-calendar mr-1"></i>${new Date(result.completed).toLocaleString()}</span>
                                ${result.results?.execution_time_seconds ? 
                                    `<span class="ml-4"><i class="fas fa-clock mr-1"></i>${result.results.execution_time_seconds}s</span>` : 
                                    ''}
                            </div>
                            ${result.error ? `
                                <div class="mt-2 text-sm text-red-600 dark:text-red-400">
                                    <i class="fas fa-exclamation-triangle mr-1"></i>${result.error}
                                </div>
                            ` : ''}
                        </div>
                        <div class="flex space-x-2 ml-4">
                            <button class="text-primary-600 hover:text-primary-800 p-2 rounded" 
                                    onclick="app.viewResultDetails('${result.test_id}')" title="View Details">
                                <i class="fas fa-eye"></i>
                            </button>
                            ${result.export_file ? `
                                <button class="text-green-600 hover:text-green-800 p-2 rounded" 
                                        onclick="app.downloadResultFile('${result.test_id}')" title="Download Export">
                                    <i class="fas fa-download"></i>
                                </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `).join('');
    }

    getStatusBadgeClass(status) {
        const classes = {
            'completed': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
            'failed': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
            'running': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
        };
        return classes[status] || 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200';
    }

    updateResultsCharts(results) {
        // Check if Chart.js is available
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js not available, skipping chart updates');
            return;
        }
        this.createResultsPieChart(results);
        this.createTrendsLineChart(results);
    }

    createResultsPieChart(results) {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js not available for pie chart');
            return;
        }
        
        const ctx = document.getElementById('resultsChart')?.getContext('2d');
        if (!ctx) return;

        const passed = results.filter(r => r.status === 'completed').length;
        const failed = results.filter(r => r.status === 'failed').length;

        if (this.charts.results) {
            this.charts.results.destroy();
        }

        this.charts.results = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Passed', 'Failed'],
                datasets: [{
                    data: [passed, failed],
                    backgroundColor: ['#22c55e', '#ef4444'],
                    borderWidth: 2,
                    borderColor: document.documentElement.classList.contains('dark') ? '#374151' : '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: document.documentElement.classList.contains('dark') ? '#e5e7eb' : '#374151'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Test Results Overview',
                        color: document.documentElement.classList.contains('dark') ? '#e5e7eb' : '#374151'
                    }
                }
            }
        });
    }

    createTrendsLineChart(results) {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js not available for trends chart');
            return;
        }
        
        const ctx = document.getElementById('trendsChart')?.getContext('2d');
        if (!ctx) return;

        // Group results by date
        const daily = results.reduce((acc, result) => {
            const date = new Date(result.completed).toDateString();
            if (!acc[date]) {
                acc[date] = { passed: 0, failed: 0 };
            }
            acc[date][result.status === 'completed' ? 'passed' : 'failed']++;
            return acc;
        }, {});

        const dates = Object.keys(daily).sort().slice(-7); // Last 7 days
        const passedData = dates.map(date => daily[date].passed || 0);
        const failedData = dates.map(date => daily[date].failed || 0);

        if (this.charts.trends) {
            this.charts.trends.destroy();
        }

        this.charts.trends = new Chart(ctx, {
            type: 'line',
            data: {
                labels: dates.map(date => new Date(date).toLocaleDateString()),
                datasets: [
                    {
                        label: 'Passed',
                        data: passedData,
                        borderColor: '#22c55e',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Failed',
                        data: failedData,
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)',
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: document.documentElement.classList.contains('dark') ? '#e5e7eb' : '#374151'
                        },
                        grid: {
                            color: document.documentElement.classList.contains('dark') ? '#4b5563' : '#e5e7eb'
                        }
                    },
                    x: {
                        ticks: {
                            color: document.documentElement.classList.contains('dark') ? '#e5e7eb' : '#374151'
                        },
                        grid: {
                            color: document.documentElement.classList.contains('dark') ? '#4b5563' : '#e5e7eb'
                        }
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: document.documentElement.classList.contains('dark') ? '#e5e7eb' : '#374151'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Test Trends (Last 7 Days)',
                        color: document.documentElement.classList.contains('dark') ? '#e5e7eb' : '#374151'
                    }
                }
            }
        });
    }

    async loadScreenshots() {
        try {
            const response = await fetch(`${this.API_BASE}/screenshots`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const data = await response.json();
            
            if (data && Array.isArray(data.screenshots)) {
                this.renderScreenshotGallery(data.screenshots);
            } else {
                this.renderScreenshotGallery([]);
            }
        } catch (error) {
            console.warn('Screenshots not available:', error.message);
            this.renderScreenshotGallery([]);
        }
    }

    renderScreenshotGallery(screenshots) {
        const container = document.getElementById('screenshotGallery');
        if (!container) return;

        // Ensure screenshots is an array
        if (!Array.isArray(screenshots)) {
            screenshots = [];
        }

        if (screenshots.length === 0) {
            container.innerHTML = `
                <div class="col-span-full text-center py-8 text-gray-500 dark:text-gray-400">
                    <i class="fas fa-images text-4xl mb-4"></i>
                    <p>No screenshots available</p>
                    <p class="text-sm">Screenshots will appear here after running tests</p>
                </div>
            `;
            return;
        }

        container.innerHTML = screenshots.map(screenshot => `
            <div class="bg-white dark:bg-gray-800 rounded-lg overflow-hidden shadow hover:shadow-lg transition-shadow">
                <div class="aspect-w-16 aspect-h-9">
                    <img src="${this.API_BASE}/screenshots/${screenshot.filename}" 
                         alt="${screenshot.filename}" 
                         class="w-full h-48 object-cover cursor-pointer"
                         onclick="app.viewScreenshot('${screenshot.filename}')">
                </div>
                <div class="p-4">
                    <h4 class="font-medium text-gray-900 dark:text-white truncate">${screenshot.filename}</h4>
                    <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        ${new Date(screenshot.created).toLocaleDateString()}
                    </p>
                    <div class="flex justify-between items-center mt-2">
                        <span class="text-xs text-gray-400">${this.formatFileSize(screenshot.size)}</span>
                        <button onclick="app.downloadScreenshot('${screenshot.filename}')" 
                                class="text-primary-600 hover:text-primary-800 p-1 rounded" title="Download">
                            <i class="fas fa-download"></i>
                        </button>
                    </div>
                </div>
            </div>
        `).join('');
    }

    async loadConfig() {
        try {
            const response = await fetch(`${this.API_BASE}/config`);
            const data = await response.json();
            
            this.populateConfigForm(data);
        } catch (error) {
            this.showNotification('Error loading config: ' + error.message, 'error');
        }
    }

    populateConfigForm(config) {
        // Browser settings
        document.getElementById('defaultBrowser').value = config.browser?.default || 'chrome';
        document.getElementById('headlessMode').checked = config.browser?.headless || false;
        document.getElementById('browserTimeout').value = config.browser?.timeout || 30;

        // API settings
        document.getElementById('apiTimeout').value = config.api?.timeout || 30;
        document.getElementById('verifySSL').checked = config.api?.verify_ssl !== false;
        document.getElementById('maxRetries').value = config.api?.max_retries || 3;
    }

    async loadSystemInfo() {
        try {
            const response = await fetch(`${this.API_BASE}/system/info`);
            const data = await response.json();
            
            this.updateSystemStatus(data);
        } catch (error) {
            console.error('Error loading system info:', error);
            this.updateSystemStatus({ running_tests: 0 });
        }
    }

    updateSystemStatus(info) {
        const statusDot = document.getElementById('systemStatus');
        if (statusDot) {
            statusDot.className = info.running_tests > 0 ? 
                'h-3 w-3 bg-yellow-400 rounded-full animate-pulse' : 
                'h-3 w-3 bg-green-400 rounded-full animate-pulse';
        }
    }

    updateDashboardStats(stats = {}) {
        document.getElementById('totalTests').textContent = stats.totalTests || 0;
        document.getElementById('runningTests').textContent = this.runningTests.size;
        
        // Calculate success rate
        const completed = this.testResults.filter(r => r.status === 'completed').length;
        const total = this.testResults.length;
        const successRate = total > 0 ? Math.round((completed / total) * 100) : 0;
        document.getElementById('successRate').textContent = `${successRate}%`;

        // Last run time
        const lastResult = this.testResults
            .sort((a, b) => new Date(b.completed) - new Date(a.completed))[0];
        const lastRun = lastResult ? 
            this.timeAgo(new Date(lastResult.completed)) : 
            'Never';
        document.getElementById('lastRun').textContent = lastRun;
    }

    onTabChange(tabName) {
        switch (tabName) {
            case 'results':
                this.loadResults();
                break;
            case 'screenshots':
                this.loadScreenshots();
                break;
            case 'config':
                this.loadConfig();
                break;
        }
    }

    startPolling() {
        // Poll for system updates every 10 seconds
        setInterval(() => {
            this.loadSystemInfo();
        }, 10000);
    }

    // Modal management
    showUploadModal() {
        document.getElementById('uploadModal').classList.remove('hidden');
        document.getElementById('uploadModal').classList.add('flex');
    }

    hideUploadModal() {
        document.getElementById('uploadModal').classList.add('hidden');
        document.getElementById('uploadModal').classList.remove('flex');
        document.getElementById('fileUpload').value = '';
    }

    async uploadFile() {
        const fileInput = document.getElementById('fileUpload');
        const file = fileInput.files[0];
        
        if (!file) {
            this.showNotification('Please select a file', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(`${this.API_BASE}/tests/upload`, {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                this.hideUploadModal();
                this.showNotification('File uploaded successfully', 'success');
                await this.loadTests();
            } else {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }
        } catch (error) {
            this.showNotification('Error uploading file: ' + error.message, 'error');
        }
    }

    // Utility methods
    formatFileSize(bytes) {
        const sizes = ['B', 'KB', 'MB', 'GB'];
        if (bytes === 0) return '0 B';
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
    }

    timeAgo(date) {
        const now = new Date();
        const diffInSeconds = Math.floor((now - date) / 1000);

        if (diffInSeconds < 60) return 'Just now';
        if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutes ago`;
        if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hours ago`;
        return `${Math.floor(diffInSeconds / 86400)} days ago`;
    }

    showNotification(message, type = 'info') {
        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };

        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 ${colors[type]} text-white px-6 py-4 rounded-lg shadow-lg z-50 animate-fade-in`;
        notification.innerHTML = `
            <div class="flex items-center space-x-3">
                <i class="fas fa-${type === 'error' ? 'exclamation-triangle' : type === 'success' ? 'check-circle' : 'info-circle'}"></i>
                <span>${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-white hover:text-gray-200">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

        document.body.appendChild(notification);

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }

    // Additional methods for complete functionality
    viewScreenshot(filename) {
        window.open(`${this.API_BASE}/screenshots/${filename}`, '_blank');
    }

    downloadScreenshot(filename) {
        const link = document.createElement('a');
        link.href = `${this.API_BASE}/screenshots/${filename}`;
        link.download = filename;
        link.click();
    }

    async viewResultDetails(testId) {
        try {
            const response = await fetch(`${this.API_BASE}/tests/results/${testId}`);
            const data = await response.json();
            
            // Show details in a modal or navigate to details page
            console.log('Test results:', data);
            this.showNotification('Results details logged to console', 'info');
        } catch (error) {
            this.showNotification('Error loading result details: ' + error.message, 'error');
        }
    }

    async downloadResultFile(testId) {
        try {
            const response = await fetch(`${this.API_BASE}/tests/results/${testId}`);
            const data = await response.json();
            
            if (data.export_file) {
                const link = document.createElement('a');
                link.href = data.export_file;
                link.download = `test_results_${testId}.json`;
                link.click();
            }
        } catch (error) {
            this.showNotification('Error downloading result file: ' + error.message, 'error');
        }
    }

    async exportResults() {
        try {
            const data = {
                timestamp: new Date().toISOString(),
                results: this.testResults
            };
            
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `easy_bdd_results_${new Date().toISOString().split('T')[0]}.json`;
            link.click();
            
            this.showNotification('Results exported successfully', 'success');
        } catch (error) {
            this.showNotification('Error exporting results: ' + error.message, 'error');
        }
    }

    async saveConfig() {
        try {
            const config = {
                browser: {
                    default: document.getElementById('defaultBrowser').value,
                    headless: document.getElementById('headlessMode').checked,
                    timeout: parseInt(document.getElementById('browserTimeout').value) || 30
                },
                api: {
                    timeout: parseInt(document.getElementById('apiTimeout').value) || 30,
                    verify_ssl: document.getElementById('verifySSL').checked,
                    max_retries: parseInt(document.getElementById('maxRetries').value) || 3
                }
            };

            const response = await fetch(`${this.API_BASE}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config })
            });

            if (response.ok) {
                this.showNotification('Configuration saved successfully', 'success');
            } else {
                throw new Error('Failed to save configuration');
            }
        } catch (error) {
            this.showNotification('Error saving configuration: ' + error.message, 'error');
        }
    }

    cancelRunningTest() {
        this.hideProgressModal();
        this.showNotification('Test execution cancelled', 'warning');
    }

    downloadTest(testPath) {
        const link = document.createElement('a');
        link.href = `${this.API_BASE}/tests/${testPath}`;
        link.download = testPath.split('/').pop();
        link.click();
    }
}

// Initialize the application when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new EasyBDDApp();
});