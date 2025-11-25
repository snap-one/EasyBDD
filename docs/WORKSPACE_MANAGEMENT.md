# Workspace Management

The Test Builder now supports organizing tests into folders/workspaces for better organization.

## Features

### 1. View Folder Information
- Each test now displays its workspace/folder location
- Folder names shown as badges in the test list
- Full folder path displayed in test metadata

### 2. Filter Tests by Workspace
- Dropdown selector in the test list view
- Filter to show only tests in a specific workspace
- Shows test count for each workspace
- "All Workspaces" option to view all tests

### 3. Create Custom Workspaces
- "New Workspace" button in test list view
- Provide workspace name and optional description
- Automatically creates folder structure
- Creates README.md with workspace description

### 4. Create Tests in Specific Workspaces
- Workspace selector when creating new tests
- Option to save in root or any workspace
- Tests automatically organized in correct folder
- Inherits workspace from current filter when creating

## Using the Features

### Creating a Workspace

1. Go to the test list view
2. Click "New Workspace" button
3. Enter workspace name (e.g., "API Tests", "Browser Tests")
4. Optionally add a description
5. Click "Create Workspace"

The workspace name will be sanitized (spaces replaced with underscores, lowercase).

### Creating Tests in a Workspace

**Method 1 - Using the Filter:**
1. Select a workspace from the dropdown filter
2. Click "New Test"
3. The test will automatically be created in the selected workspace

**Method 2 - Using the Selector:**
1. Click "New Test" (from any view)
2. In the Test Information section, select desired workspace
3. Fill in test details
4. Click "Save"

### Viewing Folder Information

In the test list, each test displays:
- 📁 Badge showing the workspace name (if in a workspace)
- 📁 Icon with full folder path in the metadata section
- Root-level tests don't show folder information

## API Endpoints

### List Folders
```bash
GET /api/folders
```

Response:
```json
{
  "folders": [
    {
      "name": "api_modules",
      "path": "api_modules",
      "test_count": 1,
      "description": null
    }
  ],
  "total": 8
}
```

### Create Folder
```bash
POST /api/folders?name=My%20Workspace&description=Optional%20description
```

Response:
```json
{
  "success": true,
  "folder": {
    "name": "my_workspace",
    "path": "my_workspace",
    "test_count": 0,
    "description": "Optional description"
  }
}
```

### Get Folder Info
```bash
GET /api/folders/{folder_name}
```

### List Tests in Folder
```bash
GET /api/tests?folder=my_workspace
```

### Create Test in Folder
```bash
POST /api/tests?folder=my_workspace
Content-Type: application/json

{
  "name": "My Test",
  "description": "Test description",
  "tags": ["api"],
  "steps": [...]
}
```

## File Structure

Tests are organized in the `tests/cases/` directory:

```
tests/cases/
├── api_modules/          # Workspace folder
│   ├── README.md         # Workspace description
│   └── test1.yaml
├── networking/
│   └── test2.yaml
├── my_custom_workspace/  # Custom workspace
│   ├── README.md
│   └── my_test.yaml
└── root_test.yaml        # Root-level test (no workspace)
```

## Benefits

1. **Organization**: Group related tests together
2. **Navigation**: Easy filtering and finding tests
3. **Scalability**: Manage large test suites effectively
4. **Context**: Clear workspace boundaries
5. **Collaboration**: Team members can work in separate workspaces

## Existing Workspaces

The framework comes with these default workspaces:
- `api_modules` - API module tests
- `audio` - Audio-related tests
- `dev` - Development/experimental tests
- `media` - Media tests
- `networking` - Network device tests
- `ovrc` - OvrC platform tests
- `power` - Power management tests
- `surveillance` - Surveillance tests

## Tips

- Use descriptive workspace names
- Keep workspace names short (will be displayed in UI)
- Add descriptions to help team members understand workspace purpose
- Tests can only be in one workspace at a time
- Moving tests between workspaces requires recreating them
- Workspace selector only shows when creating NEW tests (not when editing)
