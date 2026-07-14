# Custom Assertions & Validators

**Powerful assertion engine for validating API responses, data structures, and complex conditions**

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Assert Action](#assert-action)
4. [Assert JSON Schema](#assert-json-schema)
5. [Assert Response](#assert-response)
6. [Supported Operators](#supported-operators)
7. [Safe Functions](#safe-functions)
8. [Examples](#examples)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The Custom Assertions feature provides three powerful actions for validating data:

- **Assert**: Evaluate custom Python-like expressions safely
- **Assert JSON Schema**: Validate data against JSON Schema definitions
- **Assert Response**: Validate HTTP response properties (status, headers, body)

All assertions are evaluated in a **secure sandbox** that prevents dangerous operations like file I/O, imports, or arbitrary code execution.

---

## Quick Start

### Basic Assertion

```yaml
steps:
  - action: API request
    method: GET
    url: "/api/users"
    store_response: "response"
  
  - action: Assert
    expression: "response['status'] == 200"
    message: "Expected successful response"
```

### JSON Schema Validation

```yaml
steps:
  - action: API request
    method: GET
    url: "/api/users/1"
    store_response: "response"
  
  - action: Assert JSON schema
    data: "${response.data}"
    schema_file: "schemas/user.json"
```

### Response Validation

```yaml
steps:
  - action: API request
    method: GET
    url: "/api/users"
    store_response: "response"
  
  - action: Assert response
    response: "${response}"
    expect:
      status: 200
      headers:
        content-type: "application/json"
```

---

## Assert Action

Evaluates a Python-like expression and fails if it returns `False`.

### Syntax

```yaml
- action: Assert
  expression: "condition_to_test"
  message: "Custom error message (optional)"
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `expression` | Yes | Python-like expression that returns boolean |
| `message` | No | Custom error message on failure |

### Variables in Expressions

All test variables are available in the expression context:

```yaml
variables:
  min_count: 5
  api_key: "secret123"

steps:
  - action: Assert
    expression: "len(data) >= min_count"
    message: "Expected at least ${min_count} items"
```

### Example Expressions

```yaml
# Equality checks
- action: Assert
  expression: "status == 200"

# Comparison operators
- action: Assert
  expression: "len(users) > 10"

- action: Assert
  expression: "response_time <= 1000"

# Membership tests
- action: Assert
  expression: "'admin' in user['roles']"

- action: Assert
  expression: "'error' not in response"

# Complex boolean logic
- action: Assert
  expression: "status == 200 and len(data) > 0 and 'id' in data[0]"

# String operations
- action: Assert
  expression: "user['email'].endswith('@example.com')"

# Nested property access
- action: Assert
  expression: "response['data']['user']['address']['city'] == 'New York'"

# Type checking
- action: Assert
  expression: "isinstance(count, int)"

# Mathematical operations
- action: Assert
  expression: "(total_price * 0.9) <= budget"
```

---

## Assert JSON Schema

Validates data against a JSON Schema definition (Draft 7).

### Syntax

```yaml
# Using a schema file
- action: Assert JSON schema
  data: "${variable_to_validate}"
  schema_file: "path/to/schema.json"

# Using an inline schema
- action: Assert JSON schema
  data: "${variable_to_validate}"
  schema:
    type: "object"
    required: ["id", "name"]
    properties:
      id: {type: "integer"}
      name: {type: "string"}
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `data` or `response` | Yes | Data to validate (can be a variable reference) |
| `schema_file` | One of | Path to JSON Schema file (relative to project root) |
| `schema` | One of | Inline JSON Schema definition |

### Schema File Example

**File: `tests/schemas/user.json`**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "User",
  "type": "object",
  "required": ["id", "name", "email"],
  "properties": {
    "id": {
      "type": "integer",
      "minimum": 1
    },
    "name": {
      "type": "string",
      "minLength": 1
    },
    "email": {
      "type": "string",
      "format": "email"
    },
    "age": {
      "type": "integer",
      "minimum": 0,
      "maximum": 150
    }
  }
}
```

**Test:**
```yaml
- action: API request
  method: GET
  url: "/api/users/1"
  store_response: "user_response"

- action: Assert JSON schema
  data: "${user_response.data}"
  schema_file: "tests/schemas/user.json"
```

### Inline Schema Example

```yaml
- action: Assert JSON schema
  data: "${post_data}"
  schema:
    type: "object"
    required: ["title", "body", "userId"]
    properties:
      title:
        type: "string"
        minLength: 5
        maxLength: 200
      body:
        type: "string"
        minLength: 10
      userId:
        type: "integer"
        minimum: 1
      tags:
        type: "array"
        items:
          type: "string"
```

### Validation Error Details

When validation fails, you'll see:
- The specific validation error message
- The path to the failing property
- The validator that failed
- Expected vs actual values

**Example output:**
```
✗ JSON schema validation failed: 'email' is a required property
  Details: {'path': [], 'validator': 'required', 'validator_value': ['id', 'name', 'email']}
```

---

## Assert Response

Validates HTTP response properties including status code, headers, and body content.

### Syntax

```yaml
- action: Assert response
  response: "${response_variable}"
  expect:
    status: 200
    headers:
      content-type: "application/json"
    body_contains:
      - "expected text"
    body_matches: "regex_pattern"
    max_response_time: 3000
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `response` | Yes | Response variable to validate |
| `expect` or `expectations` | Yes | Dictionary of expected values |

### Expectation Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | integer | Expected HTTP status code |
| `headers` | dict | Expected header values (case-insensitive) |
| `body_contains` | string/list | Text that must appear in response body |
| `body_matches` | string | Regex pattern to match against body |
| `max_response_time` | integer | Maximum response time in milliseconds |

### Examples

**Status Code Validation:**
```yaml
- action: Assert response
  response: "${api_response}"
  expect:
    status: 200
```

**Headers Validation:**
```yaml
- action: Assert response
  response: "${api_response}"
  expect:
    status: 201
    headers:
      content-type: "application/json"
      x-api-version: "2.0"
```

**Body Content Validation:**
```yaml
- action: Assert response
  response: "${api_response}"
  expect:
    status: 200
    body_contains:
      - "success"
      - "user_id"
      - "token"
```

**Regex Pattern Matching:**
```yaml
- action: Assert response
  response: "${api_response}"
  expect:
    body_matches: '"id":\s*\d+'
```

**Response Time Validation:**
```yaml
- action: Assert response
  response: "${api_response}"
  expect:
    status: 200
    max_response_time: 500
```

**Complete Validation:**
```yaml
- action: Assert response
  response: "${login_response}"
  expect:
    status: 200
    headers:
      content-type: "application/json"
      set-cookie: "session"
    body_contains:
      - "token"
      - "user"
    max_response_time: 1000
```

---

## Supported Operators

The assertion engine supports the following operators:

### Comparison Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `==` | Equal to | `status == 200` |
| `!=` | Not equal to | `error != None` |
| `>` | Greater than | `count > 10` |
| `>=` | Greater than or equal | `age >= 18` |
| `<` | Less than | `price < 100` |
| `<=` | Less than or equal | `time <= 5000` |

### Membership Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `in` | Contains | `'admin' in roles` |
| `not in` | Does not contain | `'error' not in message` |

### Boolean Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `and` | Logical AND | `a > 0 and b < 10` |
| `or` | Logical OR | `status == 200 or status == 201` |
| `not` | Logical NOT | `not error` |

### Arithmetic Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `+` | Addition | `total + tax` |
| `-` | Subtraction | `balance - cost` |
| `*` | Multiplication | `price * quantity` |
| `/` | Division | `total / count` |
| `%` | Modulo | `number % 2 == 0` |

### Identity Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `is` | Identity check | `value is None` |
| `is not` | Negative identity | `result is not None` |

---

## Safe Functions

The following built-in Python functions are available in expressions:

### Type Functions

- `str()` - Convert to string
- `int()` - Convert to integer
- `float()` - Convert to float
- `bool()` - Convert to boolean
- `list()` - Convert to list
- `dict()` - Convert to dictionary
- `set()` - Convert to set
- `tuple()` - Convert to tuple
- `type()` - Get object type
- `isinstance()` - Check instance type

### Numeric Functions

- `len()` - Get length
- `abs()` - Absolute value
- `min()` - Minimum value
- `max()` - Maximum value
- `sum()` - Sum of iterable
- `round()` - Round number

### Collection Functions

- `sorted()` - Sort iterable
- `range()` - Generate range
- `enumerate()` - Enumerate with index
- `zip()` - Zip multiple iterables
- `any()` - Check if any true
- `all()` - Check if all true

### Substring Helpers

- `contains(container, item)` - Same as `item in container`, but casts both sides to `str()` first
- `not_contains(container, item)` - Inverse of `contains()`

Use these instead of the `'x' in str(y)` / `'x' not in str(y)` idiom when `y` (e.g. `last_response`)
might not already be a string — they read the same either way, without the extra cast:

```yaml
# Instead of: expression: "'error' not in str(last_response)"
- action: Assert
  expression: "not_contains(last_response, 'error')"

# Instead of: expression: "'${mac}' in str(last_response)"
- action: Assert
  expression: "contains(last_response, '${mac}')"
```

### Example Usage

```yaml
# Length check
- action: Assert
  expression: "len(users) >= 10"

# Type conversion
- action: Assert
  expression: "int(user_id) > 0"

# Min/max validation
- action: Assert
  expression: "max(prices) < 1000"

# Sum calculation
- action: Assert
  expression: "sum(quantities) == total_quantity"

# Sorted check
- action: Assert
  expression: "ids == sorted(ids)"

# Any/all checks
- action: Assert
  expression: "all(user['active'] for user in users)"
```

---

## Examples

### API Response Validation

```yaml
name: "API Validation Example"
variables:
  api_url: "https://api.example.com"

steps:
  - action: API request
    method: GET
    url: "${api_url}/users"
    store_response: "users_response"
  
  # Validate status
  - action: Assert
    expression: "users_response['status'] == 200"
  
  # Validate data structure
  - action: Assert
    expression: "isinstance(users_response['data'], list)"
  
  # Validate minimum count
  - action: Assert
    expression: "len(users_response['data']) > 0"
  
  # Validate each user has required fields
  - action: Assert
    expression: "all('id' in user and 'name' in user for user in users_response['data'])"
  
  # Full response validation
  - action: Assert response
    response: "${users_response}"
    expect:
      status: 200
      headers:
        content-type: "application/json"
      body_contains: ["id", "name", "email"]
```

### Complex Business Logic

```yaml
name: "E-commerce Validation"
variables:
  cart_total: 0
  discount_threshold: 100
  discount_rate: 0.1

steps:
  - action: API request
    method: GET
    url: "/api/cart"
    store_response: "cart_response"
  
  # Validate cart total
  - action: Assert
    expression: "cart_response['data']['total'] >= 0"
  
  # Validate discount logic
  - action: Assert
    expression: |
      (cart_response['data']['total'] >= discount_threshold and 
       cart_response['data']['discount'] >= cart_response['data']['subtotal'] * discount_rate) or
      (cart_response['data']['total'] < discount_threshold and 
       cart_response['data']['discount'] == 0)
    message: "Discount calculation is incorrect"
  
  # Validate item quantities
  - action: Assert
    expression: "all(item['quantity'] > 0 for item in cart_response['data']['items'])"
```

### JSON Schema with Complex Nested Objects

```yaml
name: "Nested Object Validation"
steps:
  - action: API request
    method: GET
    url: "/api/order/12345"
    store_response: "order_response"
  
  - action: Assert JSON schema
    data: "${order_response.data}"
    schema:
      type: "object"
      required: ["orderId", "customer", "items", "payment"]
      properties:
        orderId:
          type: "string"
          pattern: "^ORD-[0-9]{6}$"
        customer:
          type: "object"
          required: ["id", "name", "email"]
          properties:
            id: {type: "integer"}
            name: {type: "string", minLength: 1}
            email: {type: "string", format: "email"}
            phone: {type: "string"}
        items:
          type: "array"
          minItems: 1
          items:
            type: "object"
            required: ["sku", "quantity", "price"]
            properties:
              sku: {type: "string"}
              quantity: {type: "integer", minimum: 1}
              price: {type: "number", minimum: 0}
        payment:
          type: "object"
          required: ["method", "status", "total"]
          properties:
            method: {type: "string", enum: ["card", "paypal", "bank"]}
            status: {type: "string", enum: ["pending", "completed", "failed"]}
            total: {type: "number", minimum: 0}
```

---

## Best Practices

### 1. Use Descriptive Messages

```yaml
# ❌ Bad
- action: Assert
  expression: "len(data) > 0"

# ✅ Good
- action: Assert
  expression: "len(data) > 0"
  message: "Expected API to return at least one user record"
```

### 2. Prefer Schema Validation for Structured Data

```yaml
# ❌ Bad - Multiple individual assertions
- action: Assert
  expression: "'id' in user and isinstance(user['id'], int)"
- action: Assert
  expression: "'name' in user and isinstance(user['name'], str)"
- action: Assert
  expression: "'email' in user"

# ✅ Good - Single schema validation
- action: Assert JSON schema
  data: "${user}"
  schema_file: "schemas/user.json"
```

### 3. Break Down Complex Expressions

```yaml
# ❌ Bad - Hard to debug
- action: Assert
  expression: "response['status'] == 200 and len(response['data']) > 0 and all('id' in item for item in response['data']) and response['headers']['content-type'] == 'application/json'"

# ✅ Good - Separate concerns
- action: Assert response
  response: "${response}"
  expect:
    status: 200
    headers:
      content-type: "application/json"

- action: Assert
  expression: "len(response['data']) > 0"
  message: "Expected response data to be non-empty"

- action: Assert
  expression: "all('id' in item for item in response['data'])"
  message: "Expected all items to have an ID field"
```

### 4. Use Variables for Magic Numbers

```yaml
# ❌ Bad
- action: Assert
  expression: "response_time <= 3000"

# ✅ Good
variables:
  max_response_time_ms: 3000

steps:
  - action: Assert
    expression: "response_time <= max_response_time_ms"
    message: "Response time ${response_time}ms exceeded limit of ${max_response_time_ms}ms"
```

### 5. Combine with Soft Assertions for Multiple Checks

```yaml
steps:
  # Check multiple conditions without stopping
  - action: Assert
    expression: "user['age'] >= 18"
    message: "User must be 18 or older"
    soft_assert: true
  
  - action: Assert
    expression: "'@' in user['email']"
    message: "Email must contain @ symbol"
    soft_assert: true
  
  - action: Assert
    expression: "len(user['password']) >= 8"
    message: "Password must be at least 8 characters"
    soft_assert: true
  
  - action: Check soft assertions
```

### 6. Validate Early and Often

```yaml
steps:
  - action: API request
    method: POST
    url: "/api/users"
    body: {name: "John", email: "john@example.com"}
    store_response: "create_response"
  
  # Validate immediately after request
  - action: Assert
    expression: "create_response['status'] == 201"
    message: "User creation failed"
  
  # Continue with more assertions
  - action: Assert
    expression: "'id' in create_response['data']"
    message: "Created user should have an ID"
```

---

## Troubleshooting

### Common Issues

#### 1. Variable Not Found in Context

**Error:** `Variable 'response' not found in context`

**Solution:** Ensure the variable is defined before using it in an assertion:

```yaml
# Store the response first
- action: API request
  url: "/api/users"
  store_response: "response"

# Then use it in assertions
- action: Assert
  expression: "response['status'] == 200"
```

#### 2. Expression Returns Non-Boolean

**Error:** `Expression did not return a boolean value`

**Solution:** Ensure your expression evaluates to `True` or `False`:

```yaml
# ❌ Bad - Returns a number
- action: Assert
  expression: "len(data)"

# ✅ Good - Returns boolean
- action: Assert
  expression: "len(data) > 0"
```

#### 3. JSON Schema Library Not Installed

**Error:** `jsonschema library is not installed`

**Solution:** Install the jsonschema package:

```bash
pip install jsonschema
```

Or add to `pyproject.toml`:

```toml
[tool.poetry.dependencies]
jsonschema = "^4.19.0"
```

#### 4. Schema File Not Found

**Error:** `Schema file not found: schemas/user.json`

**Solution:** Ensure the path is relative to the project root:

```yaml
# Use path relative to project root
schema_file: "tests/schemas/user.json"

# Not just the filename
schema_file: "user.json"  # ❌ Won't work
```

#### 5. Unsafe Function Call

**Error:** `Function calls are restricted for security`

**Solution:** Only use the safe functions listed in the [Safe Functions](#safe-functions) section. You cannot call arbitrary functions:

```yaml
# ❌ Bad - open() is not safe
expression: "open('file.txt').read()"

# ✅ Good - Use safe functions
expression: "len(data) > 0"
```

### Debugging Tips

1. **Print Variables for Inspection:**
   - Add a `Print variable` action before assertions to see the data

2. **Use Simpler Expressions First:**
   - Start with basic checks and add complexity gradually

3. **Check Variable Types:**
   ```yaml
   - action: Assert
     expression: "type(response).__name__ == 'dict'"
   ```

4. **Validate Schema Files:**
   - Use online validators like [jsonschemavalidator.net](https://www.jsonschemavalidator.net/)

5. **Enable Verbose Output:**
   - Check HTML reports for detailed assertion failures

---

## Summary

Custom Assertions provide powerful validation capabilities:

| Feature | Use Case |
|---------|----------|
| **Assert** | Custom boolean expressions, complex conditions |
| **Assert JSON Schema** | Structured data validation, API contracts |
| **Assert Response** | HTTP-specific validation (status, headers, body) |

All three actions integrate seamlessly with:
- Variable substitution (`${variable}`)
- Soft assertions (continue on failure)
- HTML reporting (detailed error messages)
- Test dependencies (validate prerequisites)

**Next Steps:**
- Review [examples directory](../tests/cases/) for more test cases
- Check [API Authentication Guide](api-auth-complete-guide.md) for API testing
- See [Soft Assertions](soft-assertions.md) for non-blocking validation
