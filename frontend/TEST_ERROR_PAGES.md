# Testing Error Pages

This guide shows how to test each error endpoint in the Easy BDD Test Builder.

## Quick Test Methods

### 1. Browser Testing (Easiest)

Simply navigate to these URLs in your browser while the server is running:

```bash
# Start the server first
python frontend/start_builder.py

# Then open these URLs in your browser:
```

#### Test URLs:

- **404 (Page Not Found)**: `http://localhost:8000/this-page-does-not-exist`
- **404 (API Endpoint)**: `http://localhost:8000/api/nonexistent-endpoint`
- **500 (Internal Server Error)**: Create a test endpoint that throws an error (see below)

### 2. Using curl

```bash
# Test 404
curl -i http://localhost:8000/nonexistent-page

# Test 400 (Bad Request) - Invalid JSON
curl -i -X POST http://localhost:8000/api/tests \
  -H "Content-Type: application/json" \
  -d '{"invalid": "data"}'

# Test 405 (Method Not Allowed) - POST on GET-only endpoint
curl -i -X POST http://localhost:8000/

# Test 404 (API endpoint)
curl -i http://localhost:8000/api/nonexistent-api
```

### 3. Using Python Script

Run the test script:

```bash
# Make sure server is running first
python frontend/start_builder.py

# In another terminal
python frontend/test_error_pages.py
```

### 4. Using FastAPI Docs

1. Start the server: `python frontend/start_builder.py`
2. Open: `http://localhost:8000/docs`
3. Try calling endpoints with invalid data to trigger errors

### 5. Manual Testing with Browser DevTools

1. Open browser DevTools (F12)
2. Go to Network tab
3. Navigate to a non-existent page
4. Check the response - should show HTML error page

## Testing Specific Error Codes

### 404 - Page Not Found

**Method 1: Browser**
```
http://localhost:8000/any-random-page-name
```

**Method 2: curl**
```bash
curl http://localhost:8000/nonexistent
```

**Method 3: Python**
```python
import requests
response = requests.get("http://localhost:8000/nonexistent")
print(response.status_code)  # Should be 404
print(response.text)  # Should show error page HTML
```

### 400 - Bad Request

**Method 1: Invalid JSON**
```bash
curl -X POST http://localhost:8000/api/tests \
  -H "Content-Type: application/json" \
  -d '{"invalid": "data"}'
```

**Method 2: Missing Required Fields**
```bash
curl -X POST http://localhost:8000/api/tests \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 405 - Method Not Allowed

**Test POST on GET-only endpoint:**
```bash
curl -X POST http://localhost:8000/
```

### 500 - Internal Server Error

To test 500 errors, you can temporarily add a test endpoint:

```python
@app.get("/api/test-error")
async def test_error():
    raise Exception("Test error for 500 page")
```

Then visit: `http://localhost:8000/api/test-error`

### 503 - Service Unavailable

**Test endpoint is already available:**

```bash
# Browser
http://localhost:8000/api/test-error-503

# curl
curl http://localhost:8000/api/test-error-503
```

### 502 - Bad Gateway

**Test endpoint:**
```bash
curl http://localhost:8000/api/test-error-502
```

### 504 - Gateway Timeout

**Test endpoint:**
```bash
curl http://localhost:8000/api/test-error-504
```

### 403 - Forbidden

**Test endpoint:**
```bash
curl http://localhost:8000/api/test-error-403
```

### 401 - Unauthorized

**Test endpoint:**
```bash
curl http://localhost:8000/api/test-error-401
```

## Testing Error Page Features

### Check Error Page Elements

1. **Error Code**: Should display prominently (e.g., "404")
2. **Error Title**: Should show friendly title (e.g., "Page Not Found")
3. **Error Message**: Should explain what happened
4. **Go Home Button**: Should link to `/`
5. **Go Back Button**: Should use browser history
6. **Error Details**: Should show in debug mode (if enabled)

### Verify Styling

- Dark theme matches app
- Responsive on mobile
- Icons display correctly
- Buttons are clickable

## Debug Mode

To see error details (stack traces), set debug mode:

```bash
export DEBUG=true
python frontend/start_builder.py
```

Or in code:
```python
app = FastAPI(debug=True)
```

## Common Test Scenarios

### Scenario 1: Non-existent Page
```
URL: http://localhost:8000/random-page-123
Expected: 404 error page
```

### Scenario 2: Invalid API Request
```
URL: http://localhost:8000/api/tests
Method: POST
Body: {"invalid": "data"}
Expected: 400 error page
```

### Scenario 3: Wrong HTTP Method
```
URL: http://localhost:8000/
Method: POST
Expected: 405 error page
```

### Scenario 4: Server Error
```
URL: http://localhost:8000/api/test-error
Expected: 500 error page
```

## Automated Testing

For CI/CD, you can use the test script:

```bash
# Run all tests
python frontend/test_error_pages.py

# Or integrate into pytest
pytest frontend/test_error_pages.py
```

## Tips

1. **Start the server first**: Always ensure the server is running before testing
2. **Check response headers**: Verify `Content-Type: text/html`
3. **Verify status codes**: Ensure the HTTP status code matches the error
4. **Test on different browsers**: Ensure compatibility
5. **Test mobile responsiveness**: Use browser dev tools to simulate mobile

## Troubleshooting

### Error page not showing?
- Check if exception handlers are registered
- Verify the error_pages.html template exists
- Check server logs for errors

### Wrong error code?
- Verify the exception is being raised correctly
- Check if another handler is catching it first

### Template not found?
- Ensure `frontend/static/error_pages.html` exists
- Check file permissions

