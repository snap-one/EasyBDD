# Easy BDD Framework - Feature Integration Roadmap

## Overview
This document outlines the step-by-step integration plan for advanced BDD features.

---

## ✅ Feature 3: Soft Assertions (Continue on Failure)

### Priority: HIGH
### Estimated Effort: 2-3 hours
### Status: ✅ COMPLETED (November 22, 2025)

### Description
Allow tests to continue executing even when assertions fail, collecting all failures to report at the end. This is crucial for comprehensive validation where you want to check multiple conditions without stopping at the first failure.

### Use Cases
- Form validation: Check all fields for errors instead of stopping at first invalid field
- UI verification: Validate multiple page elements in one test
- API response validation: Check multiple response fields

### Implementation Plan

**Phase 1: Core Infrastructure (30 min)**
- [ ] Add `soft_assert` tracking to test execution context
- [ ] Create `SoftAssertionManager` class in `easy_bdd/core/`
- [ ] Store soft assertion failures in list with step details

**Phase 2: Action Support (45 min)**
- [ ] Add `soft_assert: true` parameter to verification actions:
  - [ ] `Verify text`
  - [ ] `Verify element`
  - [ ] `Assert JSON`
  - [ ] `Assert response`
- [ ] Create new action: `Check soft assertions` to evaluate all collected failures

**Phase 3: Reporting (30 min)**
- [ ] Display soft assertion failures in HTML report
- [ ] Show soft assertion summary in console output
- [ ] Add soft assertion count to test statistics

**Phase 4: Documentation & Testing (45 min)**
- [ ] Create `docs/soft-assertions.md`
- [ ] Add example test cases
- [ ] Update actions.md with soft assertion parameters

### YAML Syntax
```yaml
steps:
  # These won't stop test execution
  - action: Verify text
    text: "Expected Title"
    soft_assert: true
    
  - action: Verify element
    selector: "#submit-button"
    soft_assert: true
    
  - action: API request
    url: "/api/data"
    store_response: "api_response"
  
  - action: Assert
    expression: "${api_response.status} == 200"
    soft_assert: true
    
  # This will fail the test if any soft assertions failed
  - action: Check soft assertions
```

### Files to Create/Modify
- `easy_bdd/core/soft_assertions.py` (NEW)
- `easy_bdd/core/runner.py` (MODIFY - add soft assertion context)
- `easy_bdd/core/html_reporter.py` (MODIFY - show soft assertion results)
- `docs/soft-assertions.md` (NEW)
- `tests/cases/soft_assertion_example.yaml` (NEW)

---

## 🎥 Feature 5: Video Recording on Failure

### Priority: HIGH
### Estimated Effort: 2 hours
### Status: ✅ COMPLETED (November 22, 2025)

### Description
Automatically record browser sessions as video when tests fail. Video recordings are invaluable for debugging visual issues and understanding test failures.

### Use Cases
- Debugging intermittent failures
- Understanding UI interactions that led to failure
- Sharing test failures with team members
- CI/CD pipeline failure analysis

### Implementation Plan

**Phase 1: Playwright Configuration (30 min)**
- [ ] Add video recording configuration to browser service
- [ ] Configure video recording options (size, format, quality)
- [ ] Set up conditional recording (only on failure)

**Phase 2: Video Management (45 min)**
- [ ] Store video path in test results
- [ ] Clean up videos for passing tests
- [ ] Keep videos for failed tests
- [ ] Add video size limits and retention policies

**Phase 3: HTML Report Integration (30 min)**
- [ ] Embed video player in HTML report for failed tests
- [ ] Add video download link
- [ ] Display video metadata (duration, size)

**Phase 4: Documentation (15 min)**
- [ ] Document video configuration options
- [ ] Add usage examples

### Configuration
```yaml
# config/framework.yaml
browser:
  video_recording:
    enabled: true
    mode: "on-failure"        # Options: "on-failure", "always", "never"
    dir: "reports/videos"
    size:
      width: 1280
      height: 720
    format: "webm"            # Playwright default
    retention_days: 7         # Auto-delete old videos
```

### Files to Create/Modify
- `easy_bdd/services/browser_service.py` (MODIFY - add video recording)
- `easy_bdd/core/runner.py` (MODIFY - handle video on failure)
- `easy_bdd/core/html_reporter.py` (MODIFY - embed video player)
- `config/framework.yaml` (MODIFY - add video settings)
- `docs/video-recording.md` (NEW)

---

## 🔗 Feature 6: Test Dependencies & Ordering

### Priority: MEDIUM
### Estimated Effort: 3-4 hours
### Status: 🟡 Planned

### Description
Allow tests to declare dependencies on other tests, ensuring proper execution order and skipping dependent tests if prerequisites fail.

### Use Cases
- Integration tests that require setup tests to pass first
- End-to-end flows with multiple dependent steps
- Test suites where later tests depend on earlier state
- Avoiding cascading failures

### Implementation Plan

**Phase 1: Dependency Declaration (1 hour)**
- [ ] Add `depends_on` and `priority` fields to test definition
- [ ] Parse dependency declarations from YAML
- [ ] Validate that dependent tests exist

**Phase 2: Execution Ordering (1.5 hours)**
- [ ] Create dependency graph/tree
- [ ] Implement topological sort for test ordering
- [ ] Handle circular dependencies (error detection)
- [ ] Sort by priority for independent tests

**Phase 3: Dependency Checking (1 hour)**
- [ ] Track test results during execution
- [ ] Skip tests when dependencies fail
- [ ] Mark dependent tests as "Skipped" with reason
- [ ] Report skipped tests in results

**Phase 4: Reporting & Documentation (30 min)**
- [ ] Show dependency chain in HTML report
- [ ] Display skip reasons
- [ ] Document dependency patterns

### YAML Syntax
```yaml
name: User Profile Test
description: Test user profile functionality

depends_on:                    # Won't run unless these pass
  - "User Login Test"
  - "Session Setup Test"

priority: 10                   # Higher priority runs first (default: 0)

steps:
  - action: Navigate to profile
    url: "${base_url}/profile"
```

### Files to Create/Modify
- `easy_bdd/core/dependency_manager.py` (NEW)
- `easy_bdd/core/parser.py` (MODIFY - parse depends_on and priority)
- `easy_bdd/core/runner.py` (MODIFY - order tests and check dependencies)
- `easy_bdd/core/html_reporter.py` (MODIFY - show dependencies)
- `docs/test-dependencies.md` (NEW)
- `tests/cases/dependency_example.yaml` (NEW)

---

## 🎯 Feature 8: Custom Assertions & Validators

### Priority: MEDIUM-HIGH
### Estimated Effort: 3 hours
### Status: ✅ COMPLETED (November 22, 2025)

### Description
Powerful assertion engine that supports custom expressions, JSON schema validation, and flexible comparison operators.

### Use Cases
- API response validation with complex conditions
- JSON schema validation against OpenAPI specs
- Custom business logic validation
- Mathematical comparisons and string pattern matching

### Implementation Plan

**Phase 1: Expression Evaluator (1 hour)**
- [ ] Create `AssertionEngine` class
- [ ] Safe expression evaluation (restricted globals)
- [ ] Support operators: ==, !=, >, <, >=, <=, in, not in, contains
- [ ] Support functions: len(), str(), int(), float()

**Phase 2: JSON Schema Validation (1 hour)**
- [ ] Integrate `jsonschema` library
- [ ] Add schema file loading
- [ ] Add inline schema support
- [ ] Detailed validation error messages

**Phase 3: Custom Validators (45 min)**
- [ ] Response status code validation
- [ ] Response time validation
- [ ] Header validation
- [ ] Body pattern matching (regex)

**Phase 4: Action Integration (15 min)**
- [ ] Create `Assert` action
- [ ] Create `Assert JSON schema` action
- [ ] Create `Assert response` action
- [ ] Update documentation

### YAML Syntax
```yaml
steps:
  # API request
  - action: API request
    method: GET
    url: "/api/users"
    store_response: "users_response"
  
  # Expression assertions
  - action: Assert
    expression: "len(${users_response.data}) > 0"
    message: "Expected at least one user"
  
  - action: Assert
    expression: "${users_response.status} == 200"
    message: "Expected successful response"
  
  - action: Assert
    expression: "'admin' in ${users_response.data[0].roles}"
    message: "First user should have admin role"
  
  # JSON Schema validation
  - action: Assert JSON schema
    response: "${users_response}"
    schema_file: "schemas/user_list.json"
  
  # Response validation
  - action: Assert response
    response: "${users_response}"
    expect:
      status: 200
      header:
        content-type: "application/json"
      body_contains: "success"
      response_time_ms: 1000  # Must respond in < 1 second
```

### Files to Create/Modify
- `easy_bdd/core/assertions.py` (NEW)
- `easy_bdd/core/runner.py` (MODIFY - add assertion actions)
- `requirements.txt` (ADD - jsonschema library)
- `docs/assertions.md` (NEW)
- `tests/cases/assertion_examples.yaml` (NEW)
- `tests/schemas/user_list.json` (NEW - example schema)

---

## 🪝 Feature 13: Test Hooks & Events

### Priority: MEDIUM
### Estimated Effort: 3-4 hours
### Status: 🟡 Planned

### Description
Lifecycle hooks that run at specific points during test execution, enabling powerful setup/teardown patterns and custom behaviors.

### Use Cases
- Global test setup (database seeding, test data creation)
- Per-test cleanup (clear cookies, reset state)
- Automatic screenshot capture after each test
- Performance metrics collection
- Custom logging and monitoring

### Implementation Plan

**Phase 1: Hook Infrastructure (1 hour)**
- [ ] Create `HookManager` class
- [ ] Define hook types: before_all, after_all, before_each, after_each
- [ ] Hook execution context with test metadata
- [ ] Error handling in hooks (continue or fail)

**Phase 2: Hook Configuration (1 hour)**
- [ ] Add hooks to framework.yaml (global hooks)
- [ ] Add hooks to test files (test-specific hooks)
- [ ] Support both YAML and Python hook functions
- [ ] Hook inheritance (global → test-level)

**Phase 3: Runner Integration (1.5 hours)**
- [ ] Execute before_all at test suite start
- [ ] Execute before_each before each test
- [ ] Execute after_each after each test (even on failure)
- [ ] Execute after_all at test suite end
- [ ] Pass test context to hooks

**Phase 4: Documentation & Examples (30 min)**
- [ ] Document all hook types
- [ ] Provide hook examples
- [ ] Best practices guide

### YAML Syntax

**Global Hooks (config/framework.yaml):**
```yaml
hooks:
  before_all:
    - action: API request
      method: POST
      url: "${admin_api}/test/setup"
      description: "Initialize test environment"
  
  before_each:
    - action: Clear cookies
    - action: Reset browser state
  
  after_each:
    - action: Take screenshot
      name: "test-${test_name}-final"
      condition: "always"  # Even on success
  
  after_all:
    - action: API request
      method: DELETE
      url: "${admin_api}/test/cleanup"
      description: "Clean up test data"
```

**Test-Specific Hooks:**
```yaml
name: User Management Test

hooks:
  before_test:
    - action: API request
      method: POST
      url: "/api/test-users"
      body: '{"count": 5}'
      store_response: "test_users"
  
  after_test:
    - action: API request
      method: DELETE
      url: "/api/test-users"

steps:
  - action: Login
    username: "${test_users[0].email}"
```

### Hook Context Variables
Hooks automatically receive:
- `${test_name}` - Current test name
- `${test_status}` - "passed", "failed", or "running"
- `${test_duration}` - Execution time in seconds
- `${step_count}` - Number of steps executed
- `${error_message}` - Error message if test failed

### Files to Create/Modify
- `easy_bdd/core/hooks.py` (NEW)
- `easy_bdd/core/runner.py` (MODIFY - execute hooks)
- `easy_bdd/core/parser.py` (MODIFY - parse hook definitions)
- `config/framework.yaml` (MODIFY - add global hooks)
- `docs/hooks-and-events.md` (NEW)
- `tests/cases/hooks_example.yaml` (NEW)

---

## 📋 Implementation Order & Timeline

### Sprint 1 (Week 1)
**Goal: Core validation and error handling improvements**
1. **Feature 3: Soft Assertions** (2-3 hours)
   - Day 1-2: Core implementation
   - Day 3: Testing and documentation

2. **Feature 8: Custom Assertions** (3 hours)
   - Day 3-4: Implementation
   - Day 5: Testing and documentation

### Sprint 2 (Week 2)
**Goal: Enhanced debugging and reporting**
3. **Feature 5: Video Recording** (2 hours)
   - Day 1: Implementation
   - Day 2: Testing and documentation

### Sprint 3 (Week 3)
**Goal: Test orchestration and lifecycle management**
4. **Feature 6: Test Dependencies** (3-4 hours)
   - Day 1-2: Core dependency system
   - Day 3: Testing and edge cases
   - Day 4: Documentation

5. **Feature 13: Test Hooks** (3-4 hours)
   - Day 4-5: Hook infrastructure
   - Day 6: Testing and documentation

---

## Success Criteria

### Feature 3: Soft Assertions
- ✅ Tests continue after assertion failures
- ✅ All failures collected and reported
- ✅ HTML report shows soft assertion summary
- ✅ Console output distinguishes soft vs hard failures

### Feature 5: Video Recording
- ✅ Videos recorded only on test failure
- ✅ Videos embedded in HTML report
- ✅ Videos auto-deleted for passing tests
- ✅ Video size/retention configurable

### Feature 6: Test Dependencies
- ✅ Tests execute in correct order based on dependencies
- ✅ Dependent tests skipped when prerequisites fail
- ✅ Circular dependencies detected and reported
- ✅ Priority-based ordering for independent tests

### Feature 8: Custom Assertions
- ✅ Expression evaluation works safely
- ✅ JSON schema validation integrated
- ✅ Clear error messages for failed assertions
- ✅ Works with API responses and variables

### Feature 13: Test Hooks
- ✅ All hook types execute at correct times
- ✅ Hooks receive proper test context
- ✅ Global and test-specific hooks both work
- ✅ Hook failures handled appropriately

---

## Dependencies & Requirements

### Python Libraries
```txt
# Existing
playwright>=1.40.0
pyyaml>=6.0
requests>=2.31.0

# New for Feature 8
jsonschema>=4.20.0

# Optional for advanced features
pytest>=7.4.0  # For test discovery patterns
```

### Minimum Framework Version
- Python 3.10+
- Playwright 1.40+

---

## Risk Mitigation

### Backward Compatibility
- All new features are **opt-in** via YAML configuration
- Existing tests will continue to work without modification
- Default behavior unchanged

### Performance Impact
- Video recording only enabled on failure (minimal overhead)
- Soft assertions use lightweight list storage
- Dependency checking done once at test discovery

### Testing Strategy
- Unit tests for each new module
- Integration tests for feature interactions
- Backward compatibility test suite
- Performance benchmarks

---

## Documentation Checklist

For each feature:
- [ ] API/YAML syntax reference
- [ ] Usage examples (basic and advanced)
- [ ] Best practices guide
- [ ] Troubleshooting section
- [ ] Update main README.md
- [ ] Add to docs/actions.md if new actions created

---

## Notes & Considerations

### Feature Interaction Matrix
| Feature | Interacts With | Notes |
|---------|---------------|-------|
| Soft Assertions | HTML Report | Need to display collected failures |
| Video Recording | Browser Service | Requires Playwright video API |
| Test Dependencies | Test Runner | Changes execution order |
| Custom Assertions | Variables | Expression evaluation uses variable context |
| Test Hooks | All Features | Hooks can use all framework features |

### Future Enhancements
After these 5 features, consider:
- Retry logic (Feature 1)
- Conditional steps (Feature 2)
- Performance metrics (Feature 10)
- Parallel execution improvements (Feature 5)

---

**Created:** November 22, 2025  
**Last Updated:** November 22, 2025  
**Status:** Planning Phase  
**Owner:** Automation Team
