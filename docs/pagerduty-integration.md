# PagerDuty Integration

**Complete guide to integrating PagerDuty incident management with Easy BDD Framework**

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Setup & Configuration](#setup--configuration)
3. [Available Actions](#available-actions)
4. [Examples](#examples)
5. [Best Practices](#best-practices)
6. [Troubleshooting](#troubleshooting)

---

## Overview

The PagerDuty integration allows you to:
- **Create incidents** when tests fail or critical issues are detected
- **Resolve incidents** automatically when issues are fixed
- **Acknowledge incidents** to track response
- **List and query incidents** for monitoring and reporting
- **Get on-call information** for escalation
- **Manage service configurations**

### Key Features

✅ **Automatic Incident Creation** - Create incidents from test failures  
✅ **Status Management** - Resolve, acknowledge, and update incidents  
✅ **Service Integration** - Link incidents to specific PagerDuty services  
✅ **Custom Details** - Add test context and metadata to incidents  
✅ **On-Call Lookup** - Get current on-call users for escalation  
✅ **Flexible Configuration** - API key via environment or test variables  

---

## Setup & Configuration

### 1. Get Your PagerDuty API Key

1. Log in to your PagerDuty account
2. Navigate to **Configuration** → **API Access Keys**
3. Click **Create New API Key**
4. Copy the API key (starts with a token like `y+...`)

### 2. Configure API Key

#### Option A: Environment Variable (Recommended)

```bash
export PAGERDUTY_API_KEY="your-api-key-here"
```

#### Option B: Test Variables

```yaml
variables:
  pagerduty_api_key: "your-api-key-here"
  pagerduty_service_id: "P123456"  # Your service ID
```

#### Option C: Per-Action Configuration

```yaml
steps:
  - action: pagerduty.create_incident
    api_key: "your-api-key-here"
    service_id: "P123456"
    title: "Test failure"
```

### 3. Find Your Service ID

1. In PagerDuty, go to **Configuration** → **Services**
2. Click on your service
3. The Service ID is shown in the URL or service details (format: `P123456`)

---

## Available Actions

### Create Incident

Create a new PagerDuty incident.

```yaml
- action: pagerduty.create_incident
  service_id: "P123456"
  title: "Test failure detected"
  description: "Critical test failed in production"
  severity: "critical"  # critical, error, warning, info
  urgency: "high"  # high, low (optional, defaults based on severity)
  store_as: "incident"
```

**Parameters:**
- `service_id` (required) - PagerDuty service ID
- `title` (required) - Incident title
- `description` (optional) - Detailed description
- `severity` (optional) - critical, error, warning, info (default: error)
- `urgency` (optional) - high, low
- `priority_id` (optional) - Priority ID
- `assignees` (optional) - Comma-separated user IDs
- `escalation_policy_id` (optional) - Escalation policy ID
- `custom_details` (optional) - Key-value pairs for additional context
- `store_as` (optional) - Variable name to store incident response

### Resolve Incident

Resolve an existing incident.

```yaml
- action: pagerduty.resolve_incident
  incident_id: "P123456"
  resolution: "Issue fixed by automated test"
  store_as: "resolved_incident"
```

**Parameters:**
- `incident_id` (required) - Incident ID to resolve
- `resolution` (optional) - Resolution notes
- `store_as` (optional) - Variable name to store response

### Acknowledge Incident

Acknowledge an incident to indicate it's being worked on.

```yaml
- action: pagerduty.acknowledge_incident
  incident_id: "P123456"
  acknowledger_id: "P789012"  # Optional
  store_as: "acknowledged_incident"
```

**Parameters:**
- `incident_id` (required) - Incident ID to acknowledge
- `acknowledger_id` (optional) - User ID acknowledging (uses API key user if not provided)
- `store_as` (optional) - Variable name to store response

### Get Incident

Retrieve details of a specific incident.

```yaml
- action: pagerduty.get_incident
  incident_id: "P123456"
  store_as: "incident_details"
```

**Parameters:**
- `incident_id` (required) - Incident ID to retrieve
- `store_as` (required) - Variable name to store incident details

### List Incidents

List incidents with optional filters.

```yaml
- action: pagerduty.list_incidents
  service_ids: "P123456, P789012"  # Optional
  statuses: "triggered, acknowledged"  # Optional
  since: "2024-01-01T00:00:00Z"  # Optional
  until: "2024-01-31T23:59:59Z"  # Optional
  limit: 25  # Optional, max 100
  store_as: "incidents"
```

**Parameters:**
- `service_ids` (optional) - Comma-separated service IDs to filter
- `statuses` (optional) - Comma-separated statuses (triggered, acknowledged, resolved)
- `since` (optional) - Start date (ISO 8601 format)
- `until` (optional) - End date (ISO 8601 format)
- `limit` (optional) - Maximum results (default: 25, max: 100)
- `store_as` (required) - Variable name to store incidents list

### Update Incident

Update an existing incident.

```yaml
- action: pagerduty.update_incident
  incident_id: "P123456"
  title: "Updated title"
  description: "Updated description"
  severity: "warning"
  status: "acknowledged"
  store_as: "updated_incident"
```

**Parameters:**
- `incident_id` (required) - Incident ID to update
- `title` (optional) - New title
- `description` (optional) - New description
- `severity` (optional) - New severity level
- `urgency` (optional) - New urgency level
- `priority_id` (optional) - New priority ID
- `status` (optional) - New status (triggered, acknowledged, resolved)
- `custom_details` (optional) - Custom key-value pairs to update
- `store_as` (optional) - Variable name to store response

### Get On-Call Users

Get users currently on-call.

```yaml
- action: pagerduty.get_oncall
  schedule_ids: "P123456, P789012"  # Optional
  escalation_policy_ids: "P111222"  # Optional
  store_as: "oncall_users"
```

**Parameters:**
- `schedule_ids` (optional) - Comma-separated schedule IDs
- `escalation_policy_ids` (optional) - Comma-separated escalation policy IDs
- `store_as` (required) - Variable name to store on-call users

### Get Service

Get service details or list services.

```yaml
# Get specific service
- action: pagerduty.get_service
  service_id: "P123456"
  store_as: "service"

# List services
- action: pagerduty.get_service
  query: "production"
  limit: 25
  store_as: "services"
```

**Parameters:**
- `service_id` (optional) - Service ID (if not provided, lists all services)
- `query` (optional) - Search query for listing services
- `limit` (optional) - Maximum results when listing (default: 25, max: 100)
- `store_as` (required) - Variable name to store service(s)

---

## Examples

### Example 1: Create Incident on Test Failure

```yaml
name: "Critical Production Test"
description: "Test that creates PagerDuty incident on failure"

variables:
  pagerduty_service_id: "P123456"
  pagerduty_api_key: "${PAGERDUTY_API_KEY}"

steps:
  - action: browser.open
    url: "https://production.example.com"
  
  - action: browser.click
    selector: "#critical-button"
  
  - action: test.assert
    expression: "page_content contains 'Success'"
    message: "Critical feature not working"
  
  # Create incident if assertion fails (handled in cleanup)
cleanup:
  - action: pagerduty.create_incident
    service_id: "${pagerduty_service_id}"
    title: "Critical Production Test Failed"
    description: "Test 'Critical Production Test' failed. Manual intervention required."
    severity: "critical"
    urgency: "high"
    custom_details:
      test_name: "Critical Production Test"
      test_path: "tests/cases/critical_prod.yaml"
      failure_time: "${current_timestamp}"
    store_as: "incident"
    # Only run if test failed (use conditional steps)
```

### Example 2: Automatic Incident Resolution

```yaml
name: "Auto-Resolve Incident"
description: "Resolve PagerDuty incident when issue is fixed"

variables:
  incident_id: "P123456"  # From previous test or stored variable

steps:
  - action: browser.open
    url: "https://production.example.com/health"
  
  - action: test.assert
    expression: "page_content contains 'Healthy'"
    message: "Service is healthy"
  
  # Resolve incident if health check passes
  - action: pagerduty.resolve_incident
    incident_id: "${incident_id}"
    resolution: "Service health check passed. Issue resolved automatically."
    store_as: "resolved_incident"
  
  - action: log
    message: "Incident ${incident_id} resolved successfully"
```

### Example 3: Conditional Incident Creation

```yaml
name: "Smart Incident Management"
description: "Create incident only for critical failures"

variables:
  pagerduty_service_id: "P123456"
  failure_count: 0

steps:
  - action: browser.open
    url: "https://api.example.com/status"
  
  - action: test.assert
    expression: "response_status == 200"
    message: "API should return 200"
    on_failure:
      - action: set variable
        name: "failure_count"
        value: "${failure_count + 1}"
  
  # Create incident only if failure_count >= 3
  - action: pagerduty.create_incident
    service_id: "${pagerduty_service_id}"
    title: "API Health Check Failing"
    description: "API health check failed ${failure_count} times"
    severity: "error"
    condition: "${failure_count >= 3}"
    store_as: "incident"
```

### Example 4: Get On-Call and Escalate

```yaml
name: "Escalate to On-Call"
description: "Get on-call user and create high-priority incident"

variables:
  pagerduty_service_id: "P123456"
  escalation_policy_id: "P789012"

steps:
  # Get current on-call users
  - action: pagerduty.get_oncall
    escalation_policy_ids: "${escalation_policy_id}"
    store_as: "oncall_users"
  
  - action: log
    message: "On-call users: ${oncall_users}"
  
  # Create incident and assign to on-call
  - action: pagerduty.create_incident
    service_id: "${pagerduty_service_id}"
    title: "Critical System Failure"
    description: "System requires immediate attention"
    severity: "critical"
    urgency: "high"
    escalation_policy_id: "${escalation_policy_id}"
    store_as: "critical_incident"
  
  - action: log
    message: "Incident ${critical_incident['id']} created and escalated"
```

### Example 5: Monitor and Update Incidents

```yaml
name: "Incident Monitoring"
description: "Monitor incidents and update status"

variables:
  pagerduty_service_id: "P123456"

steps:
  # List all triggered incidents
  - action: pagerduty.list_incidents
    service_ids: "${pagerduty_service_id}"
    statuses: "triggered, acknowledged"
    limit: 10
    store_as: "active_incidents"
  
  - action: log
    message: "Found ${len(active_incidents)} active incidents"
  
  # Process each incident
  - action: loop
    items: "${active_incidents}"
    item_var: "incident"
    steps:
      - action: log
        message: "Processing incident: ${incident['id']} - ${incident['title']}"
      
      # Update incident with test context
      - action: pagerduty.update_incident
        incident_id: "${incident['id']}"
        custom_details:
          last_checked: "${current_timestamp}"
          test_status: "monitoring"
          checked_by: "automated_test"
        store_as: "updated_incident"
```

### Example 6: Integration with Test Results

```yaml
name: "Test Failure to PagerDuty"
description: "Create incident when test suite fails"

variables:
  pagerduty_service_id: "P123456"
  test_suite_name: "Production Smoke Tests"

steps:
  - action: test.run
    test_path: "tests/cases/smoke_tests.yaml"
    store_as: "test_results"
  
  # Check if tests failed
  - action: test.assert
    expression: "test_results['success'] == True"
    message: "Test suite passed"
    on_failure:
      # Create incident for test failures
      - action: pagerduty.create_incident
        service_id: "${pagerduty_service_id}"
        title: "Test Suite Failed: ${test_suite_name}"
        description: |
          Test suite '${test_suite_name}' failed.
          
          Failed tests: ${test_results['failed']}
          Total tests: ${test_results['total_tests']}
          Success rate: ${test_results['success_rate']}%
        severity: "error"
        custom_details:
          test_suite: "${test_suite_name}"
          failed_count: "${test_results['failed']}"
          total_count: "${test_results['total_tests']}"
          success_rate: "${test_results['success_rate']}"
          execution_time: "${test_results['execution_time']}"
        store_as: "failure_incident"
      
      - action: log
        message: "Incident created: ${failure_incident['id']}"
```

---

## Best Practices

### 1. Use Environment Variables for API Keys

Never hardcode API keys in test files. Use environment variables:

```yaml
variables:
  pagerduty_api_key: "${PAGERDUTY_API_KEY}"  # From environment
  pagerduty_service_id: "${PAGERDUTY_SERVICE_ID}"  # From environment
```

### 2. Add Context with Custom Details

Include test context in custom details for better incident tracking:

```yaml
- action: pagerduty.create_incident
  custom_details:
    test_name: "${test_name}"
    test_path: "${test_path}"
    environment: "production"
    test_execution_id: "${execution_id}"
    failure_reason: "${failure_message}"
```

### 3. Use Appropriate Severity Levels

- **critical** - System down, immediate action required
- **error** - Test failures, degraded functionality
- **warning** - Non-critical issues, monitoring needed
- **info** - Informational incidents, status updates

### 4. Implement Cleanup

Always resolve incidents when issues are fixed:

```yaml
cleanup:
  - action: pagerduty.resolve_incident
    incident_id: "${incident_id}"
    resolution: "Test passed on retry. Issue resolved."
```

### 5. Monitor Incident Status

Check incident status before creating duplicates:

```yaml
- action: pagerduty.list_incidents
  service_ids: "${pagerduty_service_id}"
  statuses: "triggered, acknowledged"
  store_as: "existing_incidents"

- action: test.assert
  expression: "len(existing_incidents) == 0"
  message: "No existing incidents, creating new one"
  on_success:
    - action: pagerduty.create_incident
      # ... create incident
```

### 6. Use Store As for Incident Tracking

Store incident IDs for later reference:

```yaml
- action: pagerduty.create_incident
  store_as: "incident"
  # Later use:
  - action: pagerduty.resolve_incident
    incident_id: "${incident['id']}"
```

---

## Troubleshooting

### Error: API key not configured

**Problem:** `PagerDuty API key not configured`

**Solution:**
1. Set `PAGERDUTY_API_KEY` environment variable
2. Or provide `api_key` in test variables
3. Or pass `api_key` parameter in action

### Error: Service ID not found

**Problem:** `Service ID not found or invalid`

**Solution:**
1. Verify service ID in PagerDuty dashboard
2. Check service ID format (starts with `P` followed by alphanumeric)
3. Ensure service exists and is active

### Error: Incident creation failed

**Problem:** `Failed to create incident: 403 Forbidden`

**Solution:**
1. Check API key permissions
2. Verify API key has incident creation rights
3. Ensure service ID is correct

### Error: Rate limiting

**Problem:** `429 Too Many Requests`

**Solution:**
1. Add delays between incident operations
2. Batch operations when possible
3. Check PagerDuty rate limits in your plan

### Getting Incident IDs

To get incident IDs from responses:

```yaml
- action: pagerduty.create_incident
  store_as: "incident"
  
- action: log
  message: "Incident ID: ${incident['id']}"
  message: "Incident Number: ${incident['incident_number']}"
```

---

## Additional Resources

- [PagerDuty API Documentation](https://developer.pagerduty.com/api-reference/)
- [PagerDuty Events API](https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgx-events-api-v2-overview) (for Events API integration)
- [PagerDuty Service Management](https://support.pagerduty.com/docs/services)

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review PagerDuty API documentation
3. Check test logs for detailed error messages
4. Verify API key and service configurations

