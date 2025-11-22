#!/bin/bash

# Async Multi-Device Test Runner
# Runs multiple device tests concurrently using background processes

echo "🚀 Starting Async Multi-Device Testing..."

# Define device configurations
declare -a DEVICES=(
    "1204:RX-D46A9121077B"
    "1012:RX-D46A9121E8C0" 
    "1156:RX-D46A91272239"
)

# Function to run a single device test
run_device_test() {
    local device_config="$1"
    local endpoint_id=$(echo "$device_config" | cut -d':' -f1)
    local device_name=$(echo "$device_config" | cut -d':' -f2)
    
    echo "⚙️  [PID-$$] Starting device $endpoint_id test..."
    
    # Create temporary test file for this device
    local test_file="/tmp/device_${endpoint_id}_test.yaml"
    
    cat > "$test_file" << EOF
name: Device ${endpoint_id} Async Test
description: Async test for device endpoint ${endpoint_id}
tags:
  - browser
  - playwright
  - device-config
  - async-${endpoint_id}

variables:
  base_url: http://binary:SnapAV704@192.168.100.8
  page: "unit"
  endpoint_id: "${endpoint_id}"
  device_name: "${device_name}"

steps:
  - action: Open browser
    url: \${base_url}/\${page}/\${endpoint_id}
    description: Open device configuration page
  
  - action: Take screenshot
    name: async_device_\${endpoint_id}_loaded
    description: Capture device page after loading
  
  - action: Fill form field
    field: '[role="textbox"][name="Name"]'
    value: \${device_name}
    description: Enter device name
  
  - action: Wait for element
    selector: .btn.btn-outline:not([disabled])
    state: visible
    timeout: 10000
    description: Wait for button to become enabled
  
  - action: Click element
    selector: .btn.btn-outline
    description: Click the outline button
  
  - action: Take screenshot
    name: async_device_\${endpoint_id}_configured
    description: Capture page after configuration
  
  - action: Verify text
    text: \${device_name}
    description: Verify device name appears on page
EOF
    
    # Run the test and capture result
    local start_time=$(date +%s)
    local result_file="/tmp/device_${endpoint_id}_result.txt"
    
    if .venv/bin/python -m easy_bdd run "$test_file" --headless > "$result_file" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        echo "✅ [PID-$$] Device $endpoint_id PASSED (${duration}s)"
        echo "PASSED:$endpoint_id:$duration" > "/tmp/device_${endpoint_id}_status.txt"
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        echo "❌ [PID-$$] Device $endpoint_id FAILED (${duration}s)"
        echo "FAILED:$endpoint_id:$duration" > "/tmp/device_${endpoint_id}_status.txt"
        echo "   Error details in $result_file"
    fi
    
    # Cleanup
    rm -f "$test_file"
}

# Start all device tests in parallel
echo "📡 Launching ${#DEVICES[@]} concurrent device tests..."
pids=()

for device_config in "${DEVICES[@]}"; do
    run_device_test "$device_config" &
    pids+=($!)
    sleep 1  # Small delay to avoid race conditions
done

echo "⏳ Waiting for all tests to complete..."

# Wait for all background processes to finish
for pid in "${pids[@]}"; do
    wait $pid
done

# Collect and display results
echo ""
echo "📊 ASYNC EXECUTION RESULTS:"
echo "================================"

passed=0
failed=0
total_time=0

for device_config in "${DEVICES[@]}"; do
    endpoint_id=$(echo "$device_config" | cut -d':' -f1)
    status_file="/tmp/device_${endpoint_id}_status.txt"
    
    if [[ -f "$status_file" ]]; then
        status_content=$(cat "$status_file")
        status=$(echo "$status_content" | cut -d':' -f1)
        device_id=$(echo "$status_content" | cut -d':' -f2)
        duration=$(echo "$status_content" | cut -d':' -f3)
        
        total_time=$((total_time + duration))
        
        if [[ "$status" == "PASSED" ]]; then
            echo "✅ Device $device_id: PASSED (${duration}s)"
            ((passed++))
        else
            echo "❌ Device $device_id: FAILED (${duration}s)"
            ((failed++))
        fi
        
        # Cleanup status file
        rm -f "$status_file"
    else
        echo "⚠️  Device $endpoint_id: Unknown status"
        ((failed++))
    fi
done

echo "================================"
echo "✅ Passed: $passed"
echo "❌ Failed: $failed"
echo "⏱️  Total execution time: ${total_time}s"

if [[ $passed -eq ${#DEVICES[@]} ]]; then
    echo "🎉 ALL TESTS PASSED!"
    exit 0
else
    echo "💥 SOME TESTS FAILED!"
    exit 1
fi