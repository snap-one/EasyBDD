#!/bin/bash
# Device Onboarding Script
# Usage: ./scripts/onboard_device.sh <device_ip> <device_type> <device_name>

DEVICE_IP=$1
DEVICE_TYPE=$2
DEVICE_NAME=${3:-"${DEVICE_TYPE}_$(echo $DEVICE_IP | tr '.' '_')"}

echo "🚀 Onboarding new device: $DEVICE_NAME ($DEVICE_IP)"

# Step 1: Auto-discover device capabilities
echo "🔍 Discovering device capabilities..."
python3 scripts/device_discovery.py --ip $DEVICE_IP --type $DEVICE_TYPE --name $DEVICE_NAME

# Step 2: Run onboarding test template
echo "🧪 Running onboarding tests..."
python -m easy_bdd run tests/templates/device_onboarding.yaml --device $DEVICE_NAME

# Step 3: Run security audit
echo "🔒 Running security audit..."
python -m easy_bdd run tests/templates/security_audit.yaml --device $DEVICE_NAME

# Step 4: Generate test report
echo "📊 Generating device profile..."
python -m easy_bdd generate-profile --device $DEVICE_NAME --output "reports/device_profiles/"

echo "✅ Device onboarding complete!"
echo "📁 Device config: config/devices/${DEVICE_NAME}.yaml"
echo "📊 Test report: reports/device_profiles/${DEVICE_NAME}_profile.html"