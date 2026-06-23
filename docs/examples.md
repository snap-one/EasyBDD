# Examples Gallery

Real-world examples using flush-left step syntax, as written in TestRail Preconditions fields.

---

## Basic Examples

### Simple Web Test

```
name: Basic Web Navigation
tags: [web, basic]

variables:
site_url: "https://example.com"

steps:
- browser.open:
url: ${site_url}
- browser.screenshot:
name: "homepage"
- browser.verify_text:
text: "Example Domain"
```

### Login Test

```
name: User Login Test
tags: [auth, critical]

variables:
app_url: "https://app.example.com"
username: "test@example.com"
password: "TestPass123"

steps:
- browser.open:
url: ${app_url}/login
- browser.fill:
selector: "[name='email']"
value: ${username}
- browser.fill:
selector: "[name='password']"
value: ${password}
- browser.click:
selector: "[type='submit']"
- browser.wait_for:
selector: ".dashboard"
- browser.verify_text:
text: "Welcome"
- browser.screenshot:
name: "dashboard"
```

### API Login and Assert

```
name: API Token Test
tags: [api, auth]

variables:
api_url: "https://api.example.com"

steps:
- api.post:
url: ${api_url}/system/login
body: {user: "${username}", password: "${password}"}
store_as: login_response
- test.assert:
value: ${last_status_code}
equals: 200
- eval.run:
expression: "login_response.data.restful_res.token"
store_as: token
- test.assert:
expression: token is not None and len(token) > 10
message: Token should be present and non-trivial
```

---

## TestRail Preconditions Examples

These are copy-paste ready for the Preconditions field of a `Feature:` case.

### Feature: API — Login and verify status

```
# 1. Login
- api.request: {method: POST, url: "${url}/system/login", body: {user: "${username}", password: "${password}"}}
# 2. Assert login succeeded
- test.assert: {value: ${last_status_code}, equals: 200}
# 3. Extract token
- eval.run: {expression: "last_json.restful_res.token", store_as: token}
# 4. Authenticated GET
- api.request: {method: GET, url: "${url}/system/status", headers: {Authorization: "Bearer ${token}"}}
# 5. Assert response contains expected key
- test.assert: {expression: "'systemInfo' in last_json"}
```

### Feature: Browser — Login flow

```
# 1. Open login page
- browser.open:
url: ${base_url}
# 2. Fill credentials
- browser.fill:
selector: input[type="text"]
value: ${username}
- browser.fill:
selector: input[type="password"]
value: ${password}
# 3. Submit
- browser.click:
role: button
name: Log In
# 4. Confirm dashboard loaded
- browser.wait_for_element:
text: SYSTEM STATUS
- browser.screenshot:
name: post-login
```

### Feature: SSH — Firmware version check

```
# 1. Connect to device
- ssh.connect:
host: ${device_ip}
username: ${device_user}
password: ${device_pass}
timeout: 30
retry: 3
retry_delay: 10
# 2. Read firmware version
- ssh.command:
command: cat /etc/firmware_version
store_as: fw_version
# 3. Assert version
- test.assert:
value: ${fw_version}
contains: "2."
# 4. Disconnect
- ssh.disconnect: {}
```

### Feature: AWS S3 — Firmware file discovery

```
# 1. List firmware files in S3
- aws.list_files:
bucket_name: ${bucket_name}
folder_prefix: ${folder_prefix}
file_extension: .bin
store_as: firmware_files
# 2. Get latest file
- aws.get_latest:
files: ${firmware_files}
store_as: latest_firmware
# 3. Log result
- test.log:
message: "Latest firmware: ${latest_firmware.version}"
```

---

## Data-Driven Examples

### Multi-User Testing

```
name: Multi-User Account Test
tags: [users, data-driven]

variables:
app_url: "https://admin.example.com"

data:
- username: "admin@company.com"
  password: "admin123"
  expected_menu: "Admin Panel"
- username: "manager@company.com"
  password: "manager123"
  expected_menu: "Management"
- username: "user@company.com"
  password: "user123"
  expected_menu: "Dashboard"

steps:
- browser.open:
url: ${app_url}
- browser.fill:
selector: "#username"
value: ${username}
- browser.fill:
selector: "#password"
value: ${password}
- browser.click:
selector: "#login-btn"
- browser.verify_text:
text: ${expected_menu}
- browser.screenshot:
name: "${username}-dashboard"
```

### Multi-Device (Async)

```
name: Multi-Device Firmware Check
tags: [devices, async]

async_execution: true
max_workers: 3

data:
- mac: "D4:6A:91:29:0F:5A"
  product: "WB-800"
- mac: "A8:3B:76:11:CC:22"
  product: "WB-250"
- mac: "11:22:33:44:55:66"
  product: "WB-300"

steps:
- ssh.connect:
host: ${mac}
username: ${device_user}
password: ${device_pass}
timeout: 30
- ssh.command:
command: cat /etc/firmware_version
store_as: fw_version
- test.assert:
value: ${fw_version}
not_empty: true
- test.log:
message: "${product} (${mac}) — firmware: ${fw_version}"
- ssh.disconnect: {}
```

### Parameterized API endpoints

```
name: API Endpoint Validation
tags: [api, rest]

variables:
api_base: "https://api.example.com"

data:
- endpoint: "/users"
  expected_status: 200
- endpoint: "/users/123"
  expected_status: 200
- endpoint: "/users/999"
  expected_status: 404

steps:
- api.get:
url: ${api_base}${endpoint}
headers: {Authorization: "Bearer ${token}"}
- test.assert:
value: ${last_status_code}
equals: ${expected_status}
```

---

## API Testing Examples

### Login, extract token, authenticated request

```
name: Token and System Status
tags: [api, auth]

variables:
api_url: "https://192.168.30.117:8001/api"

steps:
- api.post:
url: ${api_url}/system/login
body: {user: "${username}", password: "${password}"}
store_as: login_response
- test.assert:
expression: login_response.data.restful_res.errCode == 0
message: Login should return errCode 0
- eval.run:
expression: "login_response.data.restful_res.token"
store_as: token
- api.get:
url: ${api_url}/system/status
headers: {Authorization: "Bearer ${token}"}
store_as: status_response
- test.assert:
value: ${last_status_code}
equals: 200
- test.assert:
expression: "'systemInfo' in status_response.data"
message: Response should contain systemInfo
```

### JSON schema validation

```
name: API Schema Validation
tags: [api, schema]

steps:
- api.get:
url: ${base_url}/devices/${device_id}
headers: {Authorization: "Bearer ${token}"}
store_as: device
- test.assert:
value: ${last_status_code}
equals: 200
- test.assert_schema:
value: ${device}
schema: {type: object, required: [id, status, name], properties: {id: {type: integer}, status: {type: string}, name: {type: string}}}
```

### 404 / error code test

```
name: Not Found Handling
tags: [api, negative]

steps:
- api.get:
url: ${base_url}/devices/99999
headers: {Authorization: "Bearer ${token}"}
- test.assert:
value: ${last_status_code}
equals: 404
- test.assert:
value: ${last_response}
contains: "not found"
```

---

## Browser Testing Examples

### Navigation smoke test

```
name: Navigation Smoke Test
tags: [browser, smoke]

setup:
- browser.open:
url: ${base_url}
- browser.screenshot:
name: start

steps:
- browser.click:
role: link
name: Settings
- browser.wait_for:
selector: ".settings-page"
- browser.verify_text:
selector: "h1"
text: Settings
- browser.screenshot:
name: settings-page
- browser.back: {}
- browser.wait_for:
selector: ".dashboard"

cleanup:
- browser.screenshot:
name: final-state
```

### Form validation

```
name: Form Validation Test
tags: [browser, forms]

variables:
form_url: "https://forms.example.com/contact"

data:
- test_case: "empty_fields"
  name: ""
  email: ""
  expected_error: "All fields are required"
- test_case: "invalid_email"
  name: "John Doe"
  email: "invalid-email"
  expected_error: "Please enter a valid email"

steps:
- browser.open:
url: ${form_url}
- browser.fill:
selector: "[name='name']"
value: ${name}
- browser.fill:
selector: "[name='email']"
value: ${email}
- browser.click:
selector: ".submit-btn"
- browser.verify_text:
text: ${expected_error}
- browser.screenshot:
name: "${test_case}-result"
```

---

## Firmware Resiliency Examples

### Full firmware upgrade flow

```
name: Firmware Upgrade and Verify
tags: [firmware, ssh]

steps:
# 1. Discover firmware in S3
- aws.list_files:
bucket_name: ${bucket_name}
folder_prefix: ${folder_prefix}
file_extension: .bin
store_as: firmware_files
# 2. Pick latest
- aws.get_latest:
files: ${firmware_files}
store_as: latest_firmware
# 3. Connect to device
- ssh.connect:
host: ${device_ip}
username: ${device_user}
password: ${device_pass}
timeout: 30
retry: 5
retry_delay: 15
# 4. Read current version
- ssh.command:
command: cat /etc/firmware_version
store_as: current_version
- test.log:
message: "Current: ${current_version} | Target: ${latest_firmware.version}"
# 5. Upgrade if needed
- condition: "current_version != latest_firmware.version"
then:
- browser.open:
  url: ${base_url}/firmware
- browser.upload:
  selector: "iframe >> #firmware-input"
  file_path: ${latest_firmware.local_path}
- browser.click:
  role: button
  name: Upgrade
- test.sleep:
  seconds: 120
else:
- test.log:
  message: "Already at target version — skipping upgrade"
# 6. Reconnect and verify
- ssh.connect:
host: ${device_ip}
username: ${device_user}
password: ${device_pass}
retry: 10
retry_delay: 20
- ssh.command:
command: cat /etc/firmware_version
store_as: new_version
- test.assert:
value: ${new_version}
equals: ${latest_firmware.version}
- ssh.disconnect: {}
```

---

## Setup and Cleanup Examples

### API test with setup/teardown

```
name: Device CRUD Test
tags: [api, crud]

setup:
- api.post:
url: ${base_url}/auth/login
body: {username: "${username}", password: "${password}"}
store_as: login_response
- eval.run:
expression: "login_response.data.access_token"
store_as: token
- test.log:
message: "Auth token acquired"

steps:
- api.post:
url: ${base_url}/devices
body: {name: "test-device", mac: "${test_mac}"}
headers: {Authorization: "Bearer ${token}"}
store_as: create_response
- test.assert:
value: ${last_status_code}
in: [200, 201]
- eval.run:
expression: "create_response.data.id"
store_as: device_id
- api.get:
url: ${base_url}/devices/${device_id}
headers: {Authorization: "Bearer ${token}"}
- test.assert:
value: ${last_status_code}
equals: 200

cleanup:
- api.delete:
url: ${base_url}/devices/${device_id}
headers: {Authorization: "Bearer ${token}"}
- test.log:
message: "Test device cleaned up"
```

---

## Shared Steps Examples

### Defining a shared step (`Shared: Authenticate` in TestRail)

```
steps:
- api.post:
url: ${base_url}/auth/login
body: {username: "${API_USERNAME}", password: "${API_PASSWORD}"}
store_as: auth_response
- test.assert:
value: ${last_status_code}
equals: 200
- eval.run:
expression: "auth_response.data.access_token"
store_as: token
```

### Calling the shared step from a `Feature:` case

```
- shared_step: Authenticate
- api.get:
url: ${base_url}/devices
headers: {Authorization: "Bearer ${token}"}
store_as: devices
- test.assert:
value: ${last_status_code}
equals: 200
- test.assert:
expression: "'items' in devices.data"
message: Response should contain items list
```

---

*Mix and match patterns to build tests suited to your needs. See [Syntax Reference](./syntax.md) for the full action reference.*
