/**
 * Easy BDD Framework - Simplified Frontend
 */

class EasyBDDApp {
    constructor() {
        this.API_BASE = '/api';
        this.testResults = [];
        this.charts = {};
        this.currentTestFile = null;
        this.allTests = []; // Store all tests for filtering
        this.availableScreenshots = []; // Store available screenshots
        this.tagColors = new Map(); // Store consistent colors for tags
        this.availableColors = [
            { bg: 'bg-blue-100', text: 'text-blue-800', darkBg: 'dark:bg-blue-900', darkText: 'dark:text-blue-300' },
            { bg: 'bg-green-100', text: 'text-green-800', darkBg: 'dark:bg-green-900', darkText: 'dark:text-green-300' },
            { bg: 'bg-purple-100', text: 'text-purple-800', darkBg: 'dark:bg-purple-900', darkText: 'dark:text-purple-300' },
            { bg: 'bg-yellow-100', text: 'text-yellow-800', darkBg: 'dark:bg-yellow-900', darkText: 'dark:text-yellow-300' },
            { bg: 'bg-pink-100', text: 'text-pink-800', darkBg: 'dark:bg-pink-900', darkText: 'dark:text-pink-300' },
            { bg: 'bg-indigo-100', text: 'text-indigo-800', darkBg: 'dark:bg-indigo-900', darkText: 'dark:text-indigo-300' },
            { bg: 'bg-red-100', text: 'text-red-800', darkBg: 'dark:bg-red-900', darkText: 'dark:text-red-300' },
            { bg: 'bg-orange-100', text: 'text-orange-800', darkBg: 'dark:bg-orange-900', darkText: 'dark:text-orange-300' },
            { bg: 'bg-teal-100', text: 'text-teal-800', darkBg: 'dark:bg-teal-900', darkText: 'dark:text-teal-300' },
            { bg: 'bg-cyan-100', text: 'text-cyan-800', darkBg: 'dark:bg-cyan-900', darkText: 'dark:text-cyan-300' }
        ];
        this.colorIndex = 0;
        
        // Initialize when DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.init());
        } else {
            this.init();
        }
    }

    async init() {
        console.log('Initializing Easy BDD App...');
        
        try {
            this.setupEventListeners();
            this.setupTabNavigation();
            this.setupDarkMode();
            await this.loadTests();
            await this.loadResults();
            await this.loadSystemInfo();
            this.updateDashboardStats();
            console.log('App initialized successfully');
        } catch (error) {
            console.error('Failed to initialize app:', error);
            this.showNotification('Failed to initialize application', 'error');
        }
    }

    setupEventListeners() {
        // Test file refresh button
        document.getElementById('refreshBtn')?.addEventListener('click', () => {
            this.showNotification('Refreshing test files...', 'info');
            this.loadTests();
        });

        // Upload button
        document.getElementById('uploadBtn')?.addEventListener('click', () => {
            document.getElementById('fileUpload').click();
        });

        // File upload
        document.getElementById('fileUpload')?.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.uploadTestFile(e.target.files[0]);
            }
        });

        // Search functionality
        document.getElementById('searchTests')?.addEventListener('input', (e) => {
            this.filterTests();
        });

        // Save button in editor
        document.getElementById('saveBtn')?.addEventListener('click', () => {
            this.saveCurrentTest();
        });

        // Export results button
        document.getElementById('exportResultsBtn')?.addEventListener('click', () => {
            this.showExportDialog();
        });

        // Tab navigation
        document.querySelectorAll('[data-tab]').forEach(tab => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.tab;
                this.switchTab(target);
            });
        });
    }

    setupTabNavigation() {
        // Tab configuration mapping
        const tabConfig = {
            'testsTab': 'testsContent',
            'editorTab': 'editorContent', 
            'resultsTab': 'resultsContent',
            'screenshotsTab': 'screenshotsContent',
            'configTab': 'configContent'
        };
        
        const tabs = document.querySelectorAll('.tab-btn');
        
        tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                const tabId = e.target.id;
                const targetPanel = tabConfig[tabId];
                
                if (!targetPanel) return;
                
                // Update tab states
                tabs.forEach(t => {
                    t.classList.remove('active', 'border-primary-500', 'text-primary-600');
                    t.classList.add('border-transparent', 'text-gray-500');
                });
                
                // Hide all panels
                document.querySelectorAll('.tab-content').forEach(panel => {
                    panel.classList.add('hidden');
                });
                
                // Activate clicked tab
                e.target.classList.remove('border-transparent', 'text-gray-500');
                e.target.classList.add('active', 'border-primary-500', 'text-primary-600');
                
                // Show target panel
                const panel = document.getElementById(targetPanel);
                if (panel) {
                    panel.classList.remove('hidden');
                    
                    // Load content for specific tabs
                    if (tabId === 'resultsTab') {
                        this.loadResults();
                    } else if (tabId === 'screenshotsTab') {
                        this.loadScreenshots();
                    } else if (tabId === 'configTab') {
                        this.loadConfig();
                    }
                }
            });
        });
    }

    setupDarkMode() {
        const toggle = document.getElementById('darkModeToggle');
        if (!toggle) return;
        
        // Check for saved theme
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'dark') {
            document.documentElement.classList.add('dark');
        }
        
        toggle.addEventListener('click', () => {
            const isDark = document.documentElement.classList.toggle('dark');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
        });
    }

    getTagColor(tag) {
        if (!this.tagColors.has(tag)) {
            const colorScheme = this.availableColors[this.colorIndex % this.availableColors.length];
            this.tagColors.set(tag, colorScheme);
            this.colorIndex++;
        }
        return this.tagColors.get(tag);
    }
    
    getTagColorClasses(tag) {
        const colors = this.getTagColor(tag);
        return `${colors.bg} ${colors.text} ${colors.darkBg} ${colors.darkText}`;
    }

    async loadTests() {
        try {
            console.log('Loading tests...');
            const response = await fetch(`${this.API_BASE}/tests/files`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            console.log('Tests loaded:', data.files?.length || 0, 'tests');
            
            this.allTests = data.files || []; // Store all tests
            this.assignColorsToTags(); // Assign colors to all tags
            this.populateTagFilter();
            this.renderTestsList(this.allTests);
            this.updateDashboardStats();
        } catch (error) {
            console.error('Error loading tests:', error);
            this.showNotification('Error loading tests: ' + error.message, 'error');
            this.allTests = [];
            this.renderTestsList([]);
        }
    }
    
    assignColorsToTags() {
        // Pre-assign colors to all existing tags for consistency
        const allTags = new Set();
        this.allTests.forEach(test => {
            if (test.tags && Array.isArray(test.tags)) {
                test.tags.forEach(tag => allTags.add(tag));
            }
        });
        
        // Sort tags alphabetically to ensure consistent color assignment
        const sortedTags = Array.from(allTags).sort();
        sortedTags.forEach(tag => {
            this.getTagColor(tag); // This will assign a color if not already assigned
        });
        
        console.log(`Assigned colors to ${sortedTags.length} tags`);
    }

    populateTagFilter() {
        const tagCheckboxList = document.getElementById('tagCheckboxList');
        if (!tagCheckboxList) return;
        
        // Collect all unique tags from all tests
        const allTags = new Set();
        this.allTests.forEach(test => {
            if (test.tags && Array.isArray(test.tags)) {
                test.tags.forEach(tag => allTags.add(tag));
            }
        });
        
        // Sort tags alphabetically
        const sortedTags = Array.from(allTags).sort();
        
        // Store current selections
        const currentSelections = this.getSelectedTags();
        
        // Clear and repopulate checkboxes
        tagCheckboxList.innerHTML = '';
        sortedTags.forEach(tag => {
            const isChecked = currentSelections.includes(tag);
            const colorClasses = this.getTagColorClasses(tag);
            const checkboxHtml = `
                <label class="flex items-center space-x-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 p-2 rounded group">
                    <input type="checkbox" value="${tag}" class="tag-checkbox rounded border-gray-300 text-primary-600 focus:ring-primary-500 focus:ring-offset-0" ${isChecked ? 'checked' : ''}>
                    <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${colorClasses} group-hover:shadow-sm transition-shadow">
                        ${tag}
                    </span>
                    <span class="text-xs text-gray-500 dark:text-gray-400 ml-auto">${this.getTagCount(tag)}</span>
                </label>
            `;
            tagCheckboxList.innerHTML += checkboxHtml;
        });
        
        // Add event listeners to checkboxes
        tagCheckboxList.querySelectorAll('.tag-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                this.updateTagFilterLabel();
                this.applyFilters();
            });
        });
        
        this.updateTagFilterLabel();
        console.log(`Populated tag filter with ${sortedTags.length} tags:`, sortedTags);
    }
    
    getTagCount(tag) {
        return this.allTests.filter(test => 
            test.tags && Array.isArray(test.tags) && test.tags.includes(tag)
        ).length;
    }
    
    getSelectedTags() {
        const checkboxes = document.querySelectorAll('.tag-checkbox:checked');
        return Array.from(checkboxes).map(cb => cb.value);
    }
    
    updateTagFilterLabel() {
        const selectedTags = this.getSelectedTags();
        const label = document.getElementById('tagFilterLabel');
        
        if (!label) return;
        
        if (selectedTags.length === 0) {
            label.textContent = 'All Tags';
        } else if (selectedTags.length === 1) {
            label.textContent = selectedTags[0];
        } else {
            label.textContent = `${selectedTags.length} Tags Selected`;
        }
        
        label.title = selectedTags.length > 0 ? selectedTags.join(', ') : 'No tags selected';
    }
    
    clearTagFilters() {
        document.querySelectorAll('.tag-checkbox:checked').forEach(checkbox => {
            checkbox.checked = false;
        });
        this.updateTagFilterLabel();
        this.applyFilters();
    }

    filterTests(searchTerm) {
        // Update search but use applyFilters for actual filtering
        const searchInput = document.getElementById('testSearch');
        if (searchInput && searchTerm !== undefined) {
            searchInput.value = searchTerm;
        }
        this.applyFilters();
    }
    
    applyFilters() {
        const searchInput = document.getElementById('testSearch');
        const selectedTags = this.getSelectedTags();
        
        const searchTerm = searchInput ? searchInput.value.toLowerCase().trim() : '';
        
        let filteredTests = [...this.allTests];
        
        // Apply search filter
        if (searchTerm) {
            filteredTests = filteredTests.filter(test => {
                // Search in name
                if (test.name && test.name.toLowerCase().includes(searchTerm)) {
                    return true;
                }
                
                // Search in description
                if (test.description && test.description.toLowerCase().includes(searchTerm)) {
                    return true;
                }
                
                // Search in tags
                if (test.tags && Array.isArray(test.tags)) {
                    return test.tags.some(tag => tag.toLowerCase().includes(searchTerm));
                }
                
                // Search in filename
                if (test.filename && test.filename.toLowerCase().includes(searchTerm)) {
                    return true;
                }
                
                return false;
            });
        }
        
        // Apply tag filter (test must have ALL selected tags)
        if (selectedTags.length > 0) {
            filteredTests = filteredTests.filter(test => {
                if (!test.tags || !Array.isArray(test.tags)) return false;
                // Check if test has all selected tags
                return selectedTags.every(tag => test.tags.includes(tag));
            });
        }
        
        const hasFilters = searchTerm || selectedTags.length > 0;
        console.log(`Applied filters - Search: "${searchTerm}", Tags: [${selectedTags.join(', ')}] - ${this.allTests.length} → ${filteredTests.length} tests`);
        
        this.renderTestsList(filteredTests);
        
        if (hasFilters) {
            this.updateFilteredStats(filteredTests.length, this.allTests.length);
        } else {
            this.updateDashboardStats();
        }
    }

    renderTestsList(tests) {
        const container = document.getElementById('testsList');
        if (!container) return;

        if (!tests || tests.length === 0) {
            const searchInput = document.getElementById('testSearch');
            const selectedTags = this.getSelectedTags();
            const hasSearchFilter = searchInput && searchInput.value.trim() !== '';
            const hasTagFilter = selectedTags.length > 0;
            const isFiltering = hasSearchFilter || hasTagFilter;
            
            let filterDescription = '';
            if (hasSearchFilter && hasTagFilter) {
                const tagText = selectedTags.length === 1 ? `tag "${selectedTags[0]}"` : `tags [${selectedTags.join(', ')}]`;
                filterDescription = `search "${searchInput.value.trim()}" and ${tagText}`;
            } else if (hasSearchFilter) {
                filterDescription = `search "${searchInput.value.trim()}"`;
            } else if (hasTagFilter) {
                const tagText = selectedTags.length === 1 ? `tag "${selectedTags[0]}"` : `tags [${selectedTags.join(', ')}]`;
                filterDescription = tagText;
            }
            
            container.innerHTML = `
                <div class="text-center py-12">
                    <i class="fas fa-${isFiltering ? 'search' : 'flask'} text-6xl text-gray-300 mb-4"></i>
                    <h3 class="text-lg font-medium text-gray-500 mb-2">${isFiltering ? 'No matching tests found' : 'No tests found'}</h3>
                    <p class="text-gray-400">${isFiltering ? `No tests match ${filterDescription}` : 'Upload a test file or create a new one to get started'}</p>
                    ${isFiltering ? '<button onclick="app.clearAllFilters();" class="mt-4 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors">Clear All Filters</button>' : ''}
                </div>
            `;
            return;
        }

        container.innerHTML = tests.map(test => `
            <div class="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 hover:shadow-md transition-shadow">
                <div class="flex items-start justify-between mb-4">
                    <div class="flex-1">
                        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-2">${test.name}</h3>
                        <p class="text-gray-600 dark:text-gray-300 text-sm mb-3">YAML test file</p>
                        
                        ${test.tags && test.tags.length > 0 ? `
                            <div class="flex flex-wrap gap-1 mb-3">
                                ${test.tags.map(tag => {
                                    const colorClasses = this.getTagColorClasses(tag);
                                    return `
                                        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colorClasses} hover:shadow-sm transition-shadow cursor-default">
                                            ${tag}
                                        </span>
                                    `;
                                }).join('')}
                            </div>
                        ` : ''}
                        
                        <div class="text-xs text-gray-500 dark:text-gray-400">
                            Modified: ${new Date(test.modified).toLocaleString()}
                        </div>
                    </div>
                    
                                        <div class="flex items-center space-x-2 ml-4">
                        <button onclick="app.runTest('${test.path}')" 
                                class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm">
                            <i class="fas fa-play mr-2"></i>Run
                        </button>
                        <button onclick="app.editTest('${test.path}')" 
                                class="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors text-sm">
                            <i class="fas fa-edit mr-2"></i>Edit
                        </button>
                    </div>
                </div>
            </div>
        `).join('');
    }

    async runTest(testPath) {
        try {
            const response = await fetch(`${this.API_BASE}/tests/run`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    test_path: testPath,
                    tags: [],
                    headless: true
                })
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            
            this.showNotification('Test started successfully', 'success');
            this.monitorTestExecution(data.test_id);
        } catch (error) {
            console.error('Error starting test:', error);
            this.showNotification('Error starting test: ' + error.message, 'error');
        }
    }

    async monitorTestExecution(testId) {
        let attempts = 0;
        const maxAttempts = 10;
        
        const checkStatus = async () => {
            try {
                const response = await fetch(`${this.API_BASE}/tests/status/${testId}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const data = await response.json();
                console.log(`Test ${testId} status:`, data.status, `${data.progress || 0}%`);
                
                if (data.status === 'completed' || data.status === 'failed') {
                    this.showNotification(
                        `Test ${data.status}! Click Results tab to view details.`, 
                        data.status === 'completed' ? 'success' : 'error'
                    );
                    this.loadResults();
                    
                    // Auto-switch to Results tab
                    setTimeout(() => {
                        const resultsTab = document.getElementById('resultsTab');
                        if (resultsTab) resultsTab.click();
                    }, 1000);
                    return;
                }
                
                if (attempts++ < maxAttempts) {
                    setTimeout(checkStatus, 1000);
                }
            } catch (error) {
                console.warn('Error checking test status:', error);
                if (attempts++ < maxAttempts) {
                    setTimeout(checkStatus, 2000);
                }
            }
        };
        
        checkStatus();
    }

    async loadResults() {
        try {
            const response = await fetch(`${this.API_BASE}/tests/results`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            // Convert results object to array
            const resultsArray = data.results ? Object.values(data.results) : [];
            this.testResults = resultsArray;
            this.renderResultsList(this.testResults);
            
            // Also load screenshots
            await this.loadScreenshots();
        } catch (error) {
            console.warn('Results not available:', error.message);
            this.testResults = [];
            this.renderResultsList([]);
        }
    }
    
    async loadScreenshots() {
        try {
            const response = await fetch(`${this.API_BASE}/screenshots/list`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            this.availableScreenshots = data.screenshots || [];
            console.log(`Loaded ${this.availableScreenshots.length} screenshots`);
        } catch (error) {
            console.warn('Screenshots not available:', error.message);
            this.availableScreenshots = [];
        }
    }

    renderResultsList(results) {
        const container = document.getElementById('resultsList');
        if (!container) return;

        if (!results || results.length === 0) {
            container.innerHTML = `
                <div class="text-center py-12">
                    <i class="fas fa-chart-line text-6xl text-gray-300 mb-4"></i>
                    <h3 class="text-lg font-medium text-gray-500 mb-2">No results yet</h3>
                    <p class="text-gray-400">Run some tests to see results here</p>
                </div>
            `;
            return;
        }

        const selectAllHtml = `
            <div class="flex items-center justify-between mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                <label class="flex items-center cursor-pointer">
                    <input type="checkbox" id="selectAllResults" class="rounded border-gray-300 text-primary-600 focus:ring-primary-500 mr-2" onchange="app.toggleSelectAll(this)">
                    <span class="text-sm font-medium text-gray-700 dark:text-gray-300">Select All Results</span>
                </label>
                <span class="text-xs text-gray-500 dark:text-gray-400">
                    <span id="selectedCount">0</span> of ${results.length} selected
                </span>
            </div>
        `;
        
        const resultsHtml = results.map(result => {
            const screenshots = result.screenshots || [];
            const logs = result.logs || [];
            const steps = result.steps || [];
            const summary = result.summary || {};
            const apiSummary = result.api_summary || null;
            const testType = result.test_type || 'unknown';
            
            const screenshotSection = screenshots.length > 0 ? `
                <div class="mt-4">
                    <h5 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        <i class="fas fa-camera mr-1"></i> Screenshots (${screenshots.length})
                    </h5>
                    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                        ${screenshots.map(screenshot => `                        ${screenshots.map(screenshot => `
                            <div class=\"relative group cursor-pointer\" onclick=\"showScreenshot('${screenshot.url}', '${screenshot.description}')\">
                                <img src=\"${screenshot.url}\" alt=\"${screenshot.description}\" 
                                     class=\"w-full h-24 object-cover rounded border border-gray-200 dark:border-gray-600 
                                            hover:shadow-lg transition-shadow group-hover:ring-2 group-hover:ring-primary-500\">
                                <div class=\"absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-20 rounded transition-opacity\"></div>
                                <div class=\"absolute bottom-1 left-1 bg-black bg-opacity-70 text-white text-xs px-1 py-0.5 rounded\">
                                    Step ${screenshot.step}
                                </div>
                            </div>
                        `).join('')}
                        `).join('')}
                    </div>
                </div>
            ` : '';
            
            const stepsSection = steps.length > 0 ? `
                <div class="mt-4">
                    <h5 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        <i class="fas fa-list-ol mr-1"></i> Test Steps (${steps.length})
                    </h5>
                    <div class="space-y-1 max-h-32 overflow-y-auto">
                        ${steps.map(step => `
                            <div class="flex items-center justify-between py-1 px-2 bg-gray-50 dark:bg-gray-700 rounded text-xs">
                                <span class="flex items-center">
                                    <span class="w-4 h-4 rounded-full bg-green-500 text-white flex items-center justify-center text-xs mr-2">
                                        ${step.step}
                                    </span>
                                    ${step.action}
                                </span>
                                <div class="flex items-center space-x-2">
                                    <span class="text-green-600 dark:text-green-400">
                                        <i class="fas fa-check"></i> ${step.duration}s
                                    </span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : '';
            
            const logsSection = logs.length > 0 ? `
                <div class="mt-4">
                    <h5 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        <i class="fas fa-file-alt mr-1"></i> ${testType === 'api' ? 'API Logs' : 'Execution Logs'} (${logs.length})
                        <button onclick="toggleDetailedLogs(this)" class="ml-2 text-xs text-blue-500 hover:text-blue-700">
                            <i class="fas fa-expand-alt"></i> Details
                        </button>
                    </h5>
                    <div class="bg-gray-900 text-green-400 p-3 rounded font-mono text-xs max-h-40 overflow-y-auto logs-container">
                        ${logs.map(log => {
                            const levelColor = log.level === 'SUCCESS' ? 'text-green-400' : 
                                             log.level === 'ERROR' ? 'text-red-400' : 
                                             log.level === 'INFO' ? 'text-blue-400' : 'text-gray-400';
                            
                            const hasResponseBody = log.details && log.details.response_body;
                            const isHttpRequest = log.message && log.message.includes('HTTP Request:');
                            
                            return `
                                <div class="mb-2 log-entry" data-details='${JSON.stringify(log.details || {})}'>
                                    <div class="flex items-start space-x-2">
                                        <span class="text-gray-500 whitespace-nowrap">${new Date(log.timestamp).toLocaleTimeString()}</span>
                                        <span class="${levelColor}">[${log.level}]</span>
                                        <span class="flex-1">${log.message}</span>
                                        ${hasResponseBody ? `
                                            <button onclick="toggleResponseBody(this)" class="text-xs text-cyan-400 hover:text-cyan-300 ml-2">
                                                <i class="fas fa-code"></i> Response
                                            </button>
                                        ` : ''}
                                    </div>
                                    ${log.details ? `
                                        <div class="detailed-info hidden mt-1 ml-6 p-2 bg-gray-800 rounded text-xs">
                                            <div class="mb-2">
                                                <span class="text-gray-400 font-medium">Request Details:</span>
                                                <pre class="text-gray-300 whitespace-pre-wrap mt-1 text-xs">${JSON.stringify({
                                                    method: log.details.method || 'N/A',
                                                    url: log.details.url || 'N/A',
                                                    headers: log.details.headers || {},
                                                    response_time: log.details.response_time || 'N/A',
                                                    status_code: log.details.status_code || 'N/A'
                                                }, null, 2)}</pre>
                                            </div>
                                            ${hasResponseBody ? `
                                                <div class="response-body-section hidden">
                                                    <div class="flex items-center justify-between mb-2">
                                                        <span class="text-cyan-400 font-medium">Response Body:</span>
                                                        <button onclick="copyToClipboard(this)" data-copy='${JSON.stringify(log.details.response_body)}' class="text-xs text-gray-400 hover:text-gray-300">
                                                            <i class="fas fa-copy"></i> Copy JSON
                                                        </button>
                                                    </div>
                                                    <div class="bg-gray-900 border border-gray-700 rounded p-3 max-h-64 overflow-y-auto">
                                                        <pre class="text-green-400 text-xs font-mono whitespace-pre-wrap">${JSON.stringify(log.details.response_body, null, 2)}</pre>
                                                    </div>
                                                </div>
                                            ` : ''}
                                        </div>
                                    ` : ''}
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            ` : '';
            
            const summarySection = Object.keys(summary).length > 0 ? `
                <div class="mt-4">
                    <h5 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        <i class="fas fa-info-circle mr-1"></i> Test Summary
                    </h5>
                    <div class="grid grid-cols-2 gap-2 text-xs">
                        <div class="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                            <span class="text-gray-600 dark:text-gray-400">Assertions:</span>
                            <span class="font-medium ml-1">${summary.passed_assertions || 0}/${summary.total_assertions || 0}</span>
                        </div>
                        <div class="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                            <span class="text-gray-600 dark:text-gray-400">Browser:</span>
                            <span class="font-medium ml-1">${summary.browser_type || 'N/A'}</span>
                        </div>
                    </div>
                </div>
            ` : '';
            
            // Check if there's any detail content to show
            const hasDetails = stepsSection || screenshotSection || logsSection || summarySection;
            
            return `
                <div class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 mb-4">
                    <div class="flex items-center justify-between mb-3">
                        <div class="flex items-center space-x-3">
                            <input type="checkbox" class="result-checkbox rounded border-gray-300 text-primary-600 focus:ring-primary-500" data-test-id="${result.test_id}">
                            <h4 class="font-medium text-gray-900 dark:text-white">${result.test_name || 'Unknown Test'}</h4>
                            <span class="px-2 py-1 text-xs rounded-full ${
                                result.success ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300' 
                                               : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300'
                            }">
                                <i class="fas fa-${result.success ? 'check' : 'times'} mr-1"></i>
                                ${result.success ? 'PASSED' : 'FAILED'}
                            </span>
                            <span class="text-xs text-gray-500 dark:text-gray-400">
                                <i class="fas fa-clock mr-1"></i>${result.duration || 0}s
                            </span>
                        </div>
                        ${hasDetails ? `
                            <button onclick="toggleResultDetails(this)" 
                                    class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
                                <i class="fas fa-chevron-down transform transition-transform"></i>
                            </button>
                        ` : ''}
                    </div>
                    
                    <div class="text-sm text-gray-600 dark:text-gray-300 mb-2">
                        <i class="fas fa-info-circle mr-1"></i>
                        ${result.output || 'No output message'}
                    </div>
                    
                    <div class="text-xs text-gray-500 dark:text-gray-400${hasDetails ? ' mb-3' : ''}">
                        <span><i class="fas fa-calendar mr-1"></i>${new Date(result.timestamp).toLocaleString()}</span>
                        <span class="ml-4"><i class="fas fa-play mr-1"></i>ID: ${result.test_id || 'N/A'}</span>
                    </div>
                    
                    ${hasDetails ? `
                        <div class="result-details hidden">
                            ${stepsSection}
                            ${screenshotSection}
                            ${logsSection}
                            ${summarySection}
                        </div>
                    ` : ''}
                </div>
            `;
        }).join('');
        
        container.innerHTML = selectAllHtml + resultsHtml;
        
        // Add event listeners to checkboxes
        container.querySelectorAll('.result-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', () => this.updateSelectedCount());
        });
        
        // Add method to toggle result details
        window.toggleResultDetails = function(button) {
            const resultItem = button.closest('.bg-white, .dark\\:bg-gray-800');
            const details = resultItem.querySelector('.result-details');
            const icon = button.querySelector('i');
            
            if (details.classList.contains('hidden')) {
                details.classList.remove('hidden');
                icon.style.transform = 'rotate(180deg)';
            } else {
                details.classList.add('hidden');
                icon.style.transform = 'rotate(0deg)';
            }
        };
        
        // Add method to show screenshot modal
        window.showScreenshot = function(url, description) {
            // Create modal overlay
            const modal = document.createElement('div');
            modal.className = 'fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4';
            modal.innerHTML = `
                <div class="relative max-w-4xl max-h-full">
                    <img src="${url}" alt="${description}" class="max-w-full max-h-full object-contain rounded-lg shadow-2xl">
                    <button onclick="this.remove()" 
                            class="absolute top-4 right-4 bg-black bg-opacity-50 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-opacity-75 transition-opacity">
                        <i class="fas fa-times"></i>
                    </button>
                    <div class="absolute bottom-4 left-4 bg-black bg-opacity-75 text-white px-3 py-2 rounded">
                        ${description}
                    </div>
                </div>
            `;
            
            // Close modal on overlay click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.remove();
            });
            
            // Close modal on escape key
            const handleEscape = (e) => {
                if (e.key === 'Escape') {
                    modal.remove();
                    document.removeEventListener('keydown', handleEscape);
                }
            };
            document.addEventListener('keydown', handleEscape);
            
            document.body.appendChild(modal);
        };
        
        // Add method to toggle detailed logs
        window.toggleDetailedLogs = function(button) {
            const logsContainer = button.closest('.mt-4').querySelector('.logs-container');
            const detailedInfos = logsContainer.querySelectorAll('.detailed-info');
            const isExpanded = button.innerHTML.includes('compress');
            
            detailedInfos.forEach(info => {
                if (isExpanded) {
                    info.classList.add('hidden');
                } else {
                    info.classList.remove('hidden');
                }
            });
            
            button.innerHTML = isExpanded ? 
                '<i class="fas fa-expand-alt"></i> Details' : 
                '<i class="fas fa-compress-alt"></i> Hide Details';
        };
        
        // Add method to toggle response body display
        window.toggleResponseBody = function(button) {
            const logEntry = button.closest('.log-entry');
            const responseSection = logEntry.querySelector('.response-body-section');
            const isExpanded = !responseSection.classList.contains('hidden');
            
            if (isExpanded) {
                responseSection.classList.add('hidden');
                button.innerHTML = '<i class="fas fa-code"></i> Response';
            } else {
                // First show the detailed info if it's hidden
                const detailedInfo = logEntry.querySelector('.detailed-info');
                if (detailedInfo.classList.contains('hidden')) {
                    detailedInfo.classList.remove('hidden');
                }
                responseSection.classList.remove('hidden');
                button.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Response';
            }
        };
        
        // Add method to copy response data to clipboard
        window.copyToClipboard = function(button) {
            const data = button.getAttribute('data-copy');
            navigator.clipboard.writeText(data).then(() => {
                const originalHTML = button.innerHTML;
                button.innerHTML = '<i class="fas fa-check"></i> Copied!';
                button.classList.add('text-green-400');
                setTimeout(() => {
                    button.innerHTML = originalHTML;
                    button.classList.remove('text-green-400');
                }, 2000);
            }).catch(err => {
                console.error('Failed to copy: ', err);
                button.innerHTML = '<i class="fas fa-times"></i> Failed';
                button.classList.add('text-red-400');
                setTimeout(() => {
                    button.innerHTML = '<i class="fas fa-copy"></i> Copy JSON';
                    button.classList.remove('text-red-400');
                }, 2000);
            });
        };
    }

    async loadSystemInfo() {
        try {
            const response = await fetch(`${this.API_BASE}/system/info`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            // Update system info display if needed
        } catch (error) {
            console.warn('System info not available:', error.message);
        }
    }

    showExportDialog() {
        // Create export dialog modal
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md mx-4">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="text-lg font-medium text-gray-900 dark:text-white">Export Test Results</h3>
                    <button onclick="this.remove()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                
                <div class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Export Format</label>
                        <select id="exportFormatSelect" class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent dark:bg-gray-700 dark:text-white">
                            <option value="json">JSON - Detailed data with all information</option>
                            <option value="csv">CSV - Spreadsheet format for analysis</option>
                            <option value="xml">XML - Structured markup format</option>
                        </select>
                    </div>
                    
                    <div class="bg-gray-50 dark:bg-gray-700 p-3 rounded">
                        <div class="text-sm text-gray-600 dark:text-gray-300 mb-2">
                            <i class="fas fa-info-circle mr-1"></i>Export Summary
                        </div>
                        <div class="text-xs text-gray-500 dark:text-gray-400">
                            ${this.testResults.length} test result(s) will be exported
                        </div>
                    </div>
                    
                    <div class="flex justify-end space-x-3 pt-2">
                        <button onclick="this.remove()" class="px-4 py-2 text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100">
                            Cancel
                        </button>
                        <button onclick="window.easyBDDApp.exportResults()" class="bg-primary-500 text-white px-4 py-2 rounded-lg hover:bg-primary-600 transition-colors">
                            <i class="fas fa-download mr-2"></i>Export
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Close on background click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
        
        document.body.appendChild(modal);
    }

    updateFilteredStats(filtered, total) {
        // Update stats to show filtered results
        const totalElement = document.getElementById('totalTests');
        if (totalElement) {
            totalElement.textContent = `${filtered} / ${total}`;
            totalElement.title = `Showing ${filtered} of ${total} tests`;
        }
    }

    clearAllFilters() {
        // Clear search input
        const searchInput = document.getElementById('testSearch');
        if (searchInput) searchInput.value = '';
        
        // Clear all tag checkboxes
        this.clearTagFilters();
        
        // Apply filters (which will show all tests since filters are cleared)
        this.applyFilters();
    }

    async loadScreenshots() {
        try {
            const response = await fetch(`${this.API_BASE}/screenshots`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            this.renderScreenshots(data.screenshots || []);
        } catch (error) {
            console.warn('Screenshots not available:', error.message);
            this.renderScreenshots([]);
        }
    }

    renderScreenshots(screenshots) {
        const container = document.getElementById('screenshotGallery');
        if (!container) return;

        if (!screenshots || screenshots.length === 0) {
            container.innerHTML = `
                <div class="text-center py-12">
                    <i class="fas fa-camera text-6xl text-gray-300 mb-4"></i>
                    <h3 class="text-lg font-medium text-gray-500 mb-2">No screenshots available</h3>
                    <p class="text-gray-400">Run some tests to generate screenshots</p>
                </div>
            `;
            return;
        }

        container.innerHTML = screenshots.map(screenshot => `
            <div class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <img src="${this.API_BASE}/screenshots/${screenshot}" alt="Screenshot" class="w-full rounded-lg mb-2">
                <p class="text-sm text-gray-600 dark:text-gray-300">${screenshot}</p>
            </div>
        `).join('');
    }

    async loadConfig() {
        try {
            const response = await fetch(`${this.API_BASE}/config`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            this.renderConfig(data);
        } catch (error) {
            console.warn('Config not available:', error.message);
            this.renderConfig({});
        }
    }

    async editTest(testPath) {
        try {
            // Switch to editor tab first
            const editorTab = document.getElementById('editorTab');
            if (editorTab) editorTab.click();
            
            // Load the test file content
            const response = await fetch(`${this.API_BASE}/tests/file/${testPath}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            this.currentTestFile = testPath;
            
            // Display in a simple textarea editor (fallback for Monaco)
            this.setupSimpleEditor(data.content, testPath);
            
            this.showNotification(`Loaded test: ${testPath}`, 'success');
        } catch (error) {
            console.error('Error loading test file:', error);
            this.showNotification('Error loading test file: ' + error.message, 'error');
        }
    }
    
    setupSimpleEditor(content, filename) {
        const editorContainer = document.getElementById('monacoEditor');
        if (!editorContainer) return;
        
        // Replace Monaco container with a simple textarea
        editorContainer.innerHTML = `
            <div class="h-full flex flex-col">
                <div class="bg-gray-100 dark:bg-gray-800 px-4 py-2 border-b border-gray-300 dark:border-gray-600">
                    <span class="text-sm font-medium text-gray-700 dark:text-gray-300">Editing: ${filename}</span>
                </div>
                <textarea 
                    id="testEditor" 
                    class="flex-1 w-full p-4 border-0 focus:ring-0 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-mono text-sm resize-none" 
                    style="min-height: 550px;"
                >${content}</textarea>
            </div>
        `;
        
        // Setup save functionality
        this.setupEditorSave();
    }
    
    setupEditorSave() {
        const saveBtn = document.getElementById('saveTestBtn');
        if (saveBtn) {
            // Remove existing listeners
            saveBtn.onclick = null;
            
            saveBtn.addEventListener('click', async () => {
                await this.saveCurrentTest();
            });
        }
    }
    
    async saveCurrentTest() {
        if (!this.currentTestFile) {
            this.showNotification('No test file loaded', 'error');
            return;
        }
        
        const editor = document.getElementById('testEditor');
        if (!editor) {
            this.showNotification('Editor not available', 'error');
            return;
        }
        
        try {
            const content = editor.value;
            const testName = this.currentTestFile.replace('.yaml', '');
            
            const response = await fetch(`${this.API_BASE}/tests/${testName}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({content})
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            this.showNotification('Test saved successfully', 'success');
            await this.loadTests(); // Refresh the test list
        } catch (error) {
            console.error('Error saving test:', error);
            this.showNotification('Error saving test: ' + error.message, 'error');
        }
    }

    showUploadModal() {
        const modal = document.getElementById('uploadModal');
        if (modal) {
            modal.classList.remove('hidden');
            modal.classList.add('flex');
        }
    }

    showNotification(message, type = 'info') {
        console.log(`[${type.toUpperCase()}] ${message}`);
        
        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };

        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 ${colors[type]} text-white px-6 py-4 rounded-lg shadow-lg z-50`;
        notification.innerHTML = `
            <div class="flex items-center space-x-3">
                <i class="fas fa-info-circle"></i>
                <span>${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-white hover:text-gray-200">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

        document.body.appendChild(notification);

        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }

    updateDashboardStats() {
        // Update dashboard statistics
        const totalElement = document.getElementById('totalTests');
        const runningElement = document.getElementById('runningTests');
        
        if (totalElement) {
            totalElement.textContent = this.allTests?.length || 0;
        }
        
        if (runningElement) {
            runningElement.textContent = '0'; // No polling for now
        }
    }
    
    toggleSelectAll(checkbox) {
        const resultCheckboxes = document.querySelectorAll('.result-checkbox');
        resultCheckboxes.forEach(cb => cb.checked = checkbox.checked);
        this.updateSelectedCount();
    }
    
    updateSelectedCount() {
        const selectedCheckboxes = document.querySelectorAll('.result-checkbox:checked');
        const countElement = document.getElementById('selectedCount');
        if (countElement) {
            countElement.textContent = selectedCheckboxes.length;
        }
        
        // Update select all checkbox state
        const selectAllCheckbox = document.getElementById('selectAllResults');
        const allCheckboxes = document.querySelectorAll('.result-checkbox');
        if (selectAllCheckbox && allCheckboxes.length > 0) {
            selectAllCheckbox.checked = selectedCheckboxes.length === allCheckboxes.length;
            selectAllCheckbox.indeterminate = selectedCheckboxes.length > 0 && selectedCheckboxes.length < allCheckboxes.length;
        }
    }

    showExportDialog() {
        // Create export dialog modal
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md mx-4">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="text-lg font-medium text-gray-900 dark:text-white">Export Test Results</h3>
                    <button onclick="this.remove()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                
                <div class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Export Format</label>
                        <select id="exportFormatSelect" class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent dark:bg-gray-700 dark:text-white">
                            <option value="json">JSON - Detailed data with all information</option>
                            <option value="csv">CSV - Spreadsheet format for analysis</option>
                            <option value="xml">XML - Structured markup format</option>
                            <option value="html">HTML Report - Professional formatted report</option>
                            <option value="pdf">PDF Report - Printable professional report</option>
                        </select>
                    </div>
                    
                    <div class="bg-gray-50 dark:bg-gray-700 p-3 rounded">
                        <div class="text-sm text-gray-600 dark:text-gray-300 mb-2">
                            <i class="fas fa-info-circle mr-1"></i>Export Summary
                        </div>
                        <div class="text-xs text-gray-500 dark:text-gray-400">
                            ${this.testResults.length} test result(s) will be exported
                        </div>
                    </div>
                    
                    <div class="flex justify-end space-x-3 pt-2">
                        <button onclick="this.remove()" class="px-4 py-2 text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100">
                            Cancel
                        </button>
                        <button onclick="window.app.exportResults()" class="bg-primary-500 text-white px-4 py-2 rounded-lg hover:bg-primary-600 transition-colors">
                            <i class="fas fa-download mr-2"></i>Export
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Close on background click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
        
        document.body.appendChild(modal);
    }
    
    async exportResults() {
        const modal = document.querySelector('.fixed.inset-0');
        const format = document.getElementById('exportFormatSelect')?.value || 'json';
        const exportSelection = document.querySelector('input[name="exportSelection"]:checked')?.value || 'all';
        
        // Get selected test IDs if using selection mode
        let selectedIds = [];
        if (exportSelection === 'selected') {
            const checkboxes = document.querySelectorAll('.result-checkbox:checked');
            selectedIds = Array.from(checkboxes).map(cb => cb.dataset.testId);
            
            if (selectedIds.length === 0) {
                this.showNotification('Please select at least one result to export', 'warning');
                return;
            }
        }
        
        try {
            const count = exportSelection === 'all' ? this.testResults.length : selectedIds.length;
            this.showNotification(`Exporting ${count} result(s) as ${format.toUpperCase()}...`, 'info');
            
            // Use different endpoints for HTML/PDF reports vs data exports
            let url;
            if (format === 'html' || format === 'pdf') {
                url = `${this.API_BASE}/tests/results/report/${format}`;
            } else {
                url = `${this.API_BASE}/tests/results/export/${format}`;
            }
            
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`Export failed: ${response.status}`);
            }
            
            if (format === 'json') {
                // For JSON, download as file
                const data = await response.json();
                this.downloadJsonFile(data, 'test_results.json');
            } else {
                // For all other formats, download as blob
                const blob = await response.blob();
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                
                // Set appropriate filename
                const timestamp = new Date().toISOString().slice(0,19).replace(/:/g,'-');
                if (format === 'html') {
                    a.download = `test_report_${timestamp}.html`;
                } else if (format === 'pdf') {
                    a.download = `test_report_${timestamp}.pdf`;
                } else {
                    a.download = `test_results.${format}`;
                }
                
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);
            }
            
            this.showNotification(`Results exported successfully as ${format.toUpperCase()}`, 'success');
            modal?.remove();
            
        } catch (error) {
            console.error('Export error:', error);
            this.showNotification(`Export failed: ${error.message}`, 'error');
        }
    }
    
    downloadJsonFile(data, filename) {
        const jsonString = JSON.stringify(data, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }
}

// Initialize the app
const app = new EasyBDDApp();
window.app = app;