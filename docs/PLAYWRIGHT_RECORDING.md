# Playwright Test Recording

The test builder now includes a Playwright-based test recording feature that allows you to capture browser interactions in real-time without CORS restrictions.

## Features

- **Real Browser Recording**: Opens an actual Chromium browser window (no iframe limitations)
- **No CORS Issues**: Works with any website including production apps
- **Automatic Action Capture**: Records clicks, typing, navigation, and form interactions
- **Live Browser Control**: Interact with any website while actions are captured
- **Smart Selector Generation**: Automatically generates CSS selectors for elements

## How to Use

### 1. Start Recording

1. Navigate to the **Test Builder** view
2. Click the **"Record Test"** button in the toolbar
3. Enter the URL you want to start recording from (e.g., `https://app.ovrc.com`)
4. Click OK

A Chromium browser window will open and navigate to your specified URL.

### 2. Interact with the Website

Perform your test scenario in the browser:
- Click buttons, links, and elements
- Type into input fields
- Navigate between pages
- Fill out forms
- Select dropdown options

Each action you perform is automatically captured and will be added to your test.

### 3. Stop Recording

1. When you're done, return to the test builder
2. Click the **"Stop Recording"** button
3. All captured actions will be added to your test steps

### 4. Review and Edit

- Review the captured steps in your test
- Edit any parameters as needed
- Add assertions or additional steps manually
- Save your test

## Captured Actions

The recorder automatically captures:

| Browser Action | Easy BDD Action |
|---------------|----------------|
| Click element | `browser.click` |
| Type text | `browser.type` |
| Navigate to URL | `browser.navigate` |

## Smart Selector Generation

The recorder generates selectors in this priority order:

1. **ID** - `#elementId` (most reliable)
2. **Class** - `button.btn-primary`
3. **Tag** - `button` (least specific)

## Requirements

- Playwright must be installed: `pip install playwright`
- Chromium browser must be installed: `playwright install chromium`
- Both are included in `requirements_builder.txt`

## Technical Details

### Backend Endpoints

- `POST /api/recorder/start` - Start a new recording session
- `GET /api/recorder/status/{session_id}` - Check recording status
- `GET /api/recorder/actions/{session_id}` - Get recorded actions
- `POST /api/recorder/stop/{session_id}` - Stop recording and retrieve actions

### Recording Process

1. Server launches Playwright browser with injected recording scripts
2. Browser events (click, input, navigation) are captured via JavaScript
3. Actions are converted to Easy BDD format
4. Actions are stored in the recording session
5. When stopped, all actions are returned to the UI

### Security

- Recording sessions are isolated per user
- No data is sent to external servers
- Browser runs locally on your machine
- Sessions are cleaned up after stopping

## Troubleshooting

### Browser Doesn't Open

**Problem**: Clicking "Record Test" doesn't open a browser.

**Solutions**:
- Make sure Playwright browsers are installed: `playwright install chromium`
- Check server console for error messages
- Verify Playwright is in requirements: `pip install playwright`

### Actions Not Capturing

**Problem**: Performing actions but nothing is recorded.

**Solutions**:
- Some dynamic elements may not be captured automatically
- Use the Web Inspector to manually capture selectors
- Add steps manually after recording

### Recording Won't Stop

**Problem**: "Stop Recording" button not working.

**Solutions**:
- Close the browser window manually
- Refresh the test builder page
- Check server logs for errors

## Best Practices

1. **Start with a clean slate**: Create a new test before recording
2. **One scenario per recording**: Keep recordings focused on a single test case
3. **Review before saving**: Always review captured steps before saving
4. **Add assertions manually**: Recorder captures interactions, add validations after
5. **Use meaningful URLs**: Start from a known entry point

## Comparison: Web Inspector vs Playwright Recording

| Feature | Web Inspector | Playwright Recording |
|---------|---------------|---------------------|
| CORS restrictions | Yes (iframe limited) | No (real browser) |
| Works with production sites | Limited | Yes |
| Selector capture | Manual click | Automatic |
| Full workflow recording | No | Yes |
| Setup required | None | Playwright install |
| Use case | Simple sites, single selectors | Complex sites, full workflows |

## Examples

### Example 1: Login Flow

1. Click "Record Test"
2. Enter URL: `https://app.ovrc.com/login`
3. Browser opens
4. Type username in username field
5. Type password in password field
6. Click "Sign In" button
7. Wait for dashboard to load
8. Click "Stop Recording"

Result: Test with 4-5 steps capturing the entire login flow.

### Example 2: Navigation Test

1. Click "Record Test"
2. Enter URL: `https://example.com`
3. Click through various menu items
4. Navigate to different pages
5. Click "Stop Recording"

Result: Test with navigation and click actions for each menu item.

## Limitations

- Currently captures clicks and typing only
- Assertions must be added manually
- Complex JavaScript interactions may not be captured
- Selector quality depends on page HTML structure

## Future Enhancements

Planned improvements:
- Real-time step preview while recording
- WebSocket streaming of actions
- Drag-and-drop capture
- Hover action capture
- Smart assertion suggestions
- Better selector generation (XPath, data attributes)
- Video recording of test sessions
