// ============================================================================
// Purchase System - JavaScript
// ============================================================================
// Handles all API interactions and UI updates
// ============================================================================

// ============================================================================
// CONFIGURATION
// ============================================================================

const API_BASE_URL = 'http://localhost/api';
// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Make an API request with proper error handling
 * @param {string} endpoint - API endpoint
 * @param {object} options - Fetch options
 * @returns {Promise<object>} Response data
 */
async function apiRequest(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || `HTTP error! status: ${response.status}`);
        }

        return data;
    } catch (error) {
        console.error('API Request Error:', error);
        throw error;
    }
}

/**
 * Format date to readable string
 * @param {string} isoString - ISO 8601 date string
 * @returns {string} Formatted date
 */
function formatDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Format price to currency
 * @param {number} price - Price value
 * @returns {string} Formatted price
 */
function formatPrice(price) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(price);
}

/**
 * Show loading indicator
 * @param {string} elementId - ID of loading element
 */
function showLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = 'flex';
    }
}

/**
 * Hide loading indicator
 * @param {string} elementId - ID of loading element
 */
function hideLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = 'none';
    }
}

/**
 * Show result message
 * @param {string} elementId - ID of result element
 * @param {string} message - Message to display
 * @param {string} type - Message type (success, error, warning)
 */
function showResult(elementId, message, type = 'success') {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = message;
        element.className = `result ${type}`;
        element.style.display = 'block';
    }
}

/**
 * Hide result message
 * @param {string} elementId - ID of result element
 */
function hideResult(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = 'none';
    }
}

// ============================================================================
// BUTTON 1: BUY - Send a purchase request
// ============================================================================

/**
 * Handle buy button click
 * Sends purchase request to backend API
 */
async function handleBuy() {
    console.log('Buy button clicked');

    // Get user input
    const username = document.getElementById('username').value.trim();
    const userId = document.getElementById('userId').value.trim();

    // Validate input
    if (!username || !userId) {
        showResult('buyResult',
            '<h3>❌ Error</h3><p>Please enter both username and user ID.</p>',
            'error'
        );
        return;
    }

    // Disable button and show loading
    const buyButton = document.getElementById('buyButton');
    buyButton.disabled = true;
    hideResult('buyResult');
    showLoading('buyLoading');

    try {
        // Make API request
        const data = await apiRequest('/buy', {
            method: 'POST',
            body: JSON.stringify({
                username: username,
                user_id: userId
            })
        });

        console.log('Purchase successful:', data);

        // Show success message
        showResult('buyResult', `
            <h3>✅ Purchase Successful!</h3>
            <p><strong>Item:</strong> ${data.purchase.item_name}</p>
            <p><strong>Price:</strong> ${formatPrice(data.purchase.price)}</p>
            <p><strong>Time:</strong> ${formatDate(data.purchase.timestamp)}</p>
            <p><strong>Kafka Partition:</strong> ${data.kafka_partition}, <strong>Offset:</strong> ${data.kafka_offset}</p>
            <p class="mt-1">💡 Your purchase has been published to Kafka and will be processed shortly.</p>
        `, 'success');

    } catch (error) {
        console.error('Buy error:', error);
        showResult('buyResult', `
            <h3>❌ Purchase Failed</h3>
            <p>${error.message}</p>
            <p class="mt-1">Please check if the backend service is running and try again.</p>
        `, 'error');
    } finally {
        // Re-enable button and hide loading
        buyButton.disabled = false;
        hideLoading('buyLoading');
    }
}

// ============================================================================
// BUTTON 2: GET ALL USER BUYS - Display all purchase requests
// ============================================================================

/**
 * Handle get all purchases button click
 * Retrieves purchase history from backend API
 */
async function handleGetAllPurchases() {
    console.log('Get All Purchases button clicked');

    // Get user ID
    const userId = document.getElementById('userId').value.trim();

    // Validate input
    if (!userId) {
        showResult('historyResult',
            '<h3>❌ Error</h3><p>Please enter a user ID.</p>',
            'error'
        );
        return;
    }

    // Disable button and show loading
    const getAllButton = document.getElementById('getAllButton');
    getAllButton.disabled = true;
    hideResult('historyResult');
    document.getElementById('purchaseStats').style.display = 'none';
    document.getElementById('purchaseTable').style.display = 'none';
    showLoading('historyLoading');

    try {
        // Make API request
        const data = await apiRequest(`/getAllUserBuys/${userId}`);

        console.log('Purchase history retrieved:', data);

        if (data.total_purchases === 0) {
            showResult('historyResult', `
                <h3>📭 No Purchases Found</h3>
                <p>User <strong>${userId}</strong> has not made any purchases yet.</p>
                <p class="mt-1">💡 Click the "Buy Random Item" button above to make your first purchase!</p>
            `, 'warning');
            return;
        }

        // Display statistics
        displayPurchaseStats(data);

        // Display purchase table
        displayPurchaseTable(data.purchases);

        // Show success message
        showResult('historyResult', `
            <h3>✅ Purchase History Retrieved</h3>
            <p>Found <strong>${data.total_purchases}</strong> purchase(s) for <strong>${data.username || userId}</strong>.</p>
        `, 'success');

    } catch (error) {
        console.error('Get purchases error:', error);

        if (error.message.includes('404') || error.message.includes('not found')) {
            showResult('historyResult', `
                <h3>📭 No Purchases Found</h3>
                <p>User <strong>${userId}</strong> has not made any purchases yet.</p>
                <p class="mt-1">💡 Click the "Buy Random Item" button above to make your first purchase!</p>
            `, 'warning');
        } else {
            showResult('historyResult', `
                <h3>❌ Failed to Retrieve Purchases</h3>
                <p>${error.message}</p>
                <p class="mt-1">Please check if the backend services are running.</p>
            `, 'error');
        }
    } finally {
        // Re-enable button and hide loading
        getAllButton.disabled = false;
        hideLoading('historyLoading');
    }
}

/**
 * Display purchase statistics
 * @param {object} data - Purchase data from API
 */
function displayPurchaseStats(data) {
    const statsElement = document.getElementById('purchaseStats');

    statsElement.innerHTML = `
        <div class="stat-item">
            <span class="stat-value">${data.total_purchases}</span>
            <span class="stat-label">Total Purchases</span>
        </div>
        <div class="stat-item">
            <span class="stat-value">${formatPrice(data.total_spent)}</span>
            <span class="stat-label">Total Spent</span>
        </div>
        <div class="stat-item">
            <span class="stat-value">${formatPrice(data.total_spent / data.total_purchases)}</span>
            <span class="stat-label">Average Per Purchase</span>
        </div>
    `;

    statsElement.style.display = 'grid';
}

/**
 * Display purchase table
 * @param {Array} purchases - Array of purchase objects
 */
function displayPurchaseTable(purchases) {
    const tableBody = document.getElementById('purchaseTableBody');
    const tableElement = document.getElementById('purchaseTable');

    // Clear existing rows
    tableBody.innerHTML = '';

    // Add rows for each purchase (newest first, already sorted by API)
    purchases.forEach(purchase => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${purchase.item_name}</td>
            <td>${formatPrice(purchase.price)}</td>
            <td>${formatDate(purchase.timestamp)}</td>
        `;
        tableBody.appendChild(row);
    });

    tableElement.style.display = 'block';
}

// SYSTEM HEALTH CHECK

/**
 * Check system health status
 */
async function checkSystemHealth() {
    console.log('Health Check button clicked');

    const button = document.getElementById('healthCheckButton');
    const statusElement = document.getElementById('healthStatus');

    // Disable button
    button.disabled = true;
    button.textContent = '⏳ Checking...';
    statusElement.style.display = 'none';

    try {
        // Make API request
        const health = await apiRequest('/health');

        console.log('Health status:', health);

        // Display health status
        const isHealthy = health.status === 'healthy';

        statusElement.innerHTML = `
            <div class="health-item ${isHealthy ? 'healthy' : 'unhealthy'}">
                <span class="health-icon">${isHealthy ? '✅' : '❌'}</span>
                <span class="health-label">Overall Status</span>
                <span class="health-status-badge ${isHealthy ? 'healthy' : 'unhealthy'}">
                    ${health.status.toUpperCase()}
                </span>
            </div>
            
            <div class="health-item ${health.kafka_connected ? 'healthy' : 'unhealthy'}">
                <span class="health-icon">${health.kafka_connected ? '✅' : '❌'}</span>
                <span class="health-label">Kafka Connection</span>
                <span class="health-status-badge ${health.kafka_connected ? 'healthy' : 'unhealthy'}">
                    ${health.kafka_connected ? 'CONNECTED' : 'DISCONNECTED'}
                </span>
            </div>
            
            <div class="health-item ${health.customer_management_api_reachable ? 'healthy' : 'unhealthy'}">
                <span class="health-icon">${health.customer_management_api_reachable ? '✅' : '❌'}</span>
                <span class="health-label">Customer Management API</span>
                <span class="health-status-badge ${health.customer_management_api_reachable ? 'healthy' : 'unhealthy'}">
                    ${health.customer_management_api_reachable ? 'REACHABLE' : 'UNREACHABLE'}
                </span>
            </div>
            
            <div class="health-item">
                <span class="health-icon">🕒</span>
                <span class="health-label">Last Checked</span>
                <span>${formatDate(health.timestamp)}</span>
            </div>
        `;

        statusElement.style.display = 'grid';

        // Update button
        button.innerHTML = `<span class="btn-icon">${isHealthy ? '✅' : '⚠️'}</span> ${isHealthy ? 'System Healthy' : 'System Issues Detected'}`;

        setTimeout(() => {
            button.innerHTML = '<span class="btn-icon">💚</span> Check System Health';
            button.disabled = false;
        }, 3000);

    } catch (error) {
        console.error('Health check error:', error);

        statusElement.innerHTML = `
            <div class="health-item unhealthy">
                <span class="health-icon">❌</span>
                <span class="health-label">Backend Connection</span>
                <span class="health-status-badge unhealthy">FAILED</span>
            </div>
        `;
        statusElement.style.display = 'grid';

        button.innerHTML = '<span class="btn-icon">❌</span> Connection Failed';
        setTimeout(() => {
            button.innerHTML = '<span class="btn-icon">💚</span> Check System Health';
            button.disabled = false;
        }, 3000);
    }
}

// EVENT LISTENERS

/**
 * Initialize event listeners when DOM is loaded
 */
document.addEventListener('DOMContentLoaded', () => {
    console.log('Frontend initialized');

    // Button 1: Buy
    const buyButton = document.getElementById('buyButton');
    if (buyButton) {
        buyButton.addEventListener('click', handleBuy);
    }

    // Button 2: Get All Purchases
    const getAllButton = document.getElementById('getAllButton');
    if (getAllButton) {
        getAllButton.addEventListener('click', handleGetAllPurchases);
    }

    // Load Items Button
    const loadItemsButton = document.getElementById('loadItemsButton');
    if (loadItemsButton) {
        loadItemsButton.addEventListener('click', loadAvailableItems);
    }

    // Health Check Button
    const healthCheckButton = document.getElementById('healthCheckButton');
    if (healthCheckButton) {
        healthCheckButton.addEventListener('click', checkSystemHealth);
    }

    // Allow Enter key to trigger buy
    const usernameInput = document.getElementById('username');
    const userIdInput = document.getElementById('userId');

    [usernameInput, userIdInput].forEach(input => {
        if (input) {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    handleBuy();
                }
            });
        }
    });

    console.log('Event listeners attached');
    console.log('API Base URL:', API_BASE_URL);
});

// KEYBOARD SHORTCUTS (Optional Enhancement)

document.addEventListener('keydown', (e) => {
    // Alt + B = Buy
    if (e.altKey && e.key === 'b') {
        e.preventDefault();
        document.getElementById('buyButton')?.click();
    }

    // Alt + G = Get All Purchases
    if (e.altKey && e.key === 'g') {
        e.preventDefault();
        document.getElementById('getAllButton')?.click();
    }

    // Alt + H = Health Check
    if (e.altKey && e.key === 'h') {
        e.preventDefault();
        document.getElementById('healthCheckButton')?.click();
    }
});

// ============================================================================
// CONSOLE BANNER (Fun little touch)
// ============================================================================

console.log('%c🛒 Purchase System', 'font-size: 20px; font-weight: bold; color: #4f46e5;');
console.log('%cMicroservices Architecture with Kafka & MongoDB', 'font-size: 12px; color: #6b7280;');
console.log('%c\nKeyboard Shortcuts:', 'font-weight: bold; color: #10b981;');
console.log('  Alt + B  →  Buy Random Item');
console.log('  Alt + G  →  Get All Purchases');
console.log('  Alt + H  →  Health Check');
console.log('\nAPI Endpoint:', API_BASE_URL);