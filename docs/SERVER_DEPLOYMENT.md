# Server Deployment Guide

This guide explains how to deploy and run Easy BDD tests on a server while accessing local IP addresses and internal networks.

## 🎯 Common Scenarios

### Scenario 1: Server on Same Network as Target Devices

If your server is on the same local network as the devices you're testing:

**Configuration:**
```yaml
# config/framework.yaml
config:
  browser:
    headless: true  # Recommended for servers
    ignore_https_errors: true  # For self-signed certificates
    args:
      - "--ignore-certificate-errors"
      - "--ignore-ssl-errors"
      - "--allow-running-insecure-content"
      - "--disable-web-security"
```

**Test Example:**
```yaml
steps:
  - action: browser.open
    url: "http://192.168.100.8"  # Local IP - works if server is on same network
    description: "Access local device"
```

**No additional configuration needed** - the browser will access local IPs directly.

---

### Scenario 2: Server on Different Network (VPN/Tunnel Required)

If your server is on a different network, you need network connectivity:

#### Option A: VPN Connection

1. **Set up VPN** on the server to connect to the target network
2. **Verify connectivity:**
   ```bash
   ping 192.168.100.8
   curl http://192.168.100.8
   ```
3. **Run tests normally** - browser will use VPN routing

#### Option B: SSH Tunnel

Create an SSH tunnel to forward local network traffic:

```bash
# On your local machine or jump host
ssh -L 8080:192.168.100.8:80 user@server

# In your test, use localhost instead
steps:
  - action: browser.open
    url: "http://localhost:8080"  # Tunneled through SSH
```

#### Option C: WireGuard/OpenVPN

Set up a VPN tunnel between server and target network:

```bash
# Install WireGuard on server
sudo apt-get install wireguard

# Configure VPN (see WireGuard docs)
# Once connected, tests work normally
```

---

### Scenario 3: Docker/Container Deployment

If running in Docker, ensure proper network configuration:

#### Docker Network Modes

**Host Network Mode** (recommended for local IP access):
```yaml
# docker-compose.yml
version: '3.8'
services:
  easy-bdd:
    image: your-easy-bdd-image
    network_mode: "host"  # Uses host network directly
    volumes:
      - ./tests:/app/tests
      - ./reports:/app/reports
```

**Bridge Network with Extra Hosts:**
```yaml
# docker-compose.yml
version: '3.8'
services:
  easy-bdd:
    image: your-easy-bdd-image
    extra_hosts:
      - "device1:192.168.100.8"
      - "device2:192.168.100.9"
    volumes:
      - ./tests:/app/tests
      - ./reports:/app/reports
```

Then use hostnames in tests:
```yaml
steps:
  - action: browser.open
    url: "http://device1"  # Resolves to 192.168.100.8
```

---

## 🔧 Browser Configuration for Servers

### Recommended Server Configuration

```yaml
# config/framework.yaml
config:
  browser:
    default: "chrome"
    headless: true  # Always use headless on servers
    window_size: [1920, 1080]
    timeout: 60  # Longer timeout for network latency
    ignore_https_errors: true  # For internal certificates
    ignore_certificate_errors: true
    args:
      # Network access
      - "--ignore-certificate-errors"
      - "--ignore-ssl-errors"
      - "--allow-running-insecure-content"
      - "--disable-web-security"
      # Server-specific optimizations
      - "--no-sandbox"  # Required for some server environments
      - "--disable-dev-shm-usage"  # Prevents shared memory issues
      - "--disable-gpu"  # No GPU on servers
      - "--disable-software-rasterizer"
      - "--disable-extensions"
      # Network configuration
      - "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1"  # Allow all hosts
```

### Environment Variables

Set these in your server environment:

```bash
# .env or system environment
DISPLAY=:99  # For Xvfb if needed
CHROME_BIN=/usr/bin/chromium-browser
PLAYWRIGHT_BROWSERS_PATH=/usr/bin
```

---

## 🌐 Network Configuration

### Firewall Rules

Ensure your server firewall allows outbound connections:

```bash
# Ubuntu/Debian
sudo ufw allow out 80/tcp
sudo ufw allow out 443/tcp
sudo ufw allow out 8080/tcp  # If using custom ports

# Or allow all outbound (less secure)
sudo ufw default allow outgoing
```

### Security Groups (Cloud Providers)

**AWS Security Groups:**
- Allow outbound HTTP (port 80)
- Allow outbound HTTPS (port 443)
- Allow outbound to your local network IP ranges

**Azure Network Security Groups:**
- Add outbound rules for HTTP/HTTPS
- Configure VPN Gateway if needed

**GCP Firewall Rules:**
- Create egress rules for HTTP/HTTPS
- Set up VPN if accessing on-premises networks

---

## 🐳 Docker Deployment Example

### Complete Docker Setup

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy application
COPY . .

# Run with host network for local IP access
CMD ["python", "-m", "easy_bdd", "run", "tests/cases/", "--headless"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  easy-bdd:
    build: .
    network_mode: "host"  # Access local network directly
    volumes:
      - ./tests:/app/tests
      - ./reports:/app/reports
      - ./config:/app/config
    environment:
      - DISPLAY=:99
      - CHROME_BIN=/usr/bin/chromium
    command: python -m easy_bdd run tests/cases/ --headless
```

---

## 🔍 Testing Network Connectivity

### Verify Server Can Reach Local IPs

```bash
# Test HTTP connectivity
curl -v http://192.168.100.8

# Test HTTPS connectivity
curl -v -k https://192.168.100.8  # -k ignores certificate errors

# Test with timeout
timeout 5 curl http://192.168.100.8 || echo "Connection failed"

# Test DNS resolution (if using hostnames)
nslookup device.local
```

### Test Browser Access

Create a simple test to verify browser can access local IPs:

```yaml
# tests/cases/test_local_network.yaml
name: "Test Local Network Access"
description: "Verify server can access local IP addresses"

steps:
  - action: browser.open
    url: "http://192.168.100.8"
    description: "Access local device"
    
  - action: browser.take_screenshot
    name: "local_network_test"
    description: "Capture page to verify access"
    
  - action: browser.assert_page_title
    expected: ".*"  # Any title means we connected
    description: "Verify page loaded"
```

Run the test:
```bash
python -m easy_bdd run tests/cases/test_local_network.yaml --headless --ignore-https
```

---

## 🚀 Running on Cloud Servers

### AWS EC2

1. **Launch EC2 instance** with appropriate security group
2. **Configure security group:**
   - Allow outbound HTTP/HTTPS
   - Allow outbound to VPN endpoint (if using VPN)
3. **Set up VPN** (if needed):
   ```bash
   # Install and configure VPN client
   sudo apt-get install openvpn
   sudo openvpn --config client.ovpn
   ```
4. **Run tests:**
   ```bash
   python -m easy_bdd run tests/cases/ --headless
   ```

### Azure VM

1. **Create VM** with network security group
2. **Configure NSG rules** for outbound HTTP/HTTPS
3. **Set up VPN** (Azure VPN Gateway or Point-to-Site)
4. **Run tests** normally

### GCP Compute Engine

1. **Create VM instance**
2. **Configure firewall rules** for outbound traffic
3. **Set up VPN** (Cloud VPN or Interconnect)
4. **Run tests** normally

---

## 🔐 Security Considerations

### Self-Signed Certificates

For internal devices with self-signed certificates:

```yaml
# config/framework.yaml
config:
  browser:
    ignore_https_errors: true
    ignore_certificate_errors: true
    args:
      - "--ignore-certificate-errors"
      - "--ignore-ssl-errors"
      - "--ignore-certificate-errors-spki-list"
```

### Network Isolation

If you need to isolate test traffic:

```bash
# Use a separate network interface
ip route add 192.168.100.0/24 via 10.0.0.1 dev eth1

# Or use a VPN connection
```

---

## 📝 Test Configuration Examples

### Using Variables for IP Addresses

```yaml
# tests/cases/device_test.yaml
name: "Device Test"
description: "Test local device access"

variables:
  device_ip: "192.168.100.8"
  device_port: "8080"

steps:
  - action: browser.open
    url: "http://${device_ip}:${device_port}"
    description: "Access device via variable"
```

### Environment-Specific Configuration

```yaml
# config/environments/production.yaml
variables:
  device_ip: "192.168.100.8"
  api_endpoint: "http://192.168.100.8/api"

# config/environments/staging.yaml
variables:
  device_ip: "192.168.200.8"
  api_endpoint: "http://192.168.200.8/api"
```

---

## 🐛 Troubleshooting

### Browser Can't Reach Local IP

**Problem:** Tests fail with "net::ERR_CONNECTION_REFUSED"

**Solutions:**
1. **Verify network connectivity:**
   ```bash
   ping 192.168.100.8
   curl http://192.168.100.8
   ```

2. **Check firewall rules:**
   ```bash
   sudo ufw status
   sudo iptables -L
   ```

3. **Verify DNS resolution** (if using hostnames):
   ```bash
   nslookup device.local
   ```

4. **Test with browser args:**
   ```yaml
   config:
     browser:
       args:
         - "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1"
   ```

### Headless Mode Issues

**Problem:** Tests work locally but fail on server

**Solutions:**
1. **Install Xvfb** for headless display:
   ```bash
   sudo apt-get install xvfb
   export DISPLAY=:99
   Xvfb :99 -screen 0 1024x768x24 &
   ```

2. **Use proper browser args:**
   ```yaml
   config:
     browser:
       args:
         - "--no-sandbox"
         - "--disable-dev-shm-usage"
         - "--disable-gpu"
   ```

### Certificate Errors

**Problem:** HTTPS tests fail with certificate errors

**Solutions:**
1. **Enable certificate bypass:**
   ```yaml
   config:
     browser:
       ignore_https_errors: true
       args:
         - "--ignore-certificate-errors"
   ```

2. **Run with --ignore-https flag:**
   ```bash
   python -m easy_bdd run tests/cases/ --ignore-https
   ```

---

## 📚 Additional Resources

- [Browser Configuration Guide](BROWSER_CONFIG.md)
- [Network Troubleshooting](TROUBLESHOOTING.md)
- [Docker Deployment](DOCKER.md) (if available)

---

## ✅ Quick Checklist

Before deploying to a server:

- [ ] Server has network access to target IPs (same network or VPN)
- [ ] Firewall allows outbound HTTP/HTTPS
- [ ] Browser configured for headless mode
- [ ] Certificate errors handled (if using HTTPS)
- [ ] Test connectivity with simple test first
- [ ] Environment variables configured
- [ ] Docker network mode set correctly (if using Docker)
- [ ] VPN/tunnel configured (if needed)

---

**Need Help?** Check the [Troubleshooting Guide](TROUBLESHOOTING.md) or open an issue on GitHub.

