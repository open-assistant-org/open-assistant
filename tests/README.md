# Tests

Comprehensive test suite for the Open Assistant application.

## Running Tests

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

### Run All Tests

```bash
# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_settings_migration.py

# Run specific test class
pytest tests/test_settings_migration.py::TestMigration

# Run specific test function
pytest tests/test_settings_migration.py::TestMigration::test_migrate_simple_settings
```

### Run Tests by Marker

```bash
# Run only migration tests
pytest -m migration

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

### Coverage Reports

```bash
# Generate HTML coverage report
pytest --cov=src --cov-report=html

# Open coverage report (Linux/Mac)
open htmlcov/index.html

# View coverage in terminal
pytest --cov=src --cov-report=term-missing
```

## Test Structure

### test_settings_migration.py

Comprehensive tests for the settings migration system:

- **TestSettingDefinitions**: Setting registry and definitions
- **TestSettingsRepository**: Basic CRUD operations for settings
- **TestCredentialsRepository**: Encrypted credential storage
- **TestAuditLogging**: Configuration change tracking
- **TestFallbackLogic**: DB → ENV → Default fallback chain
- **TestMigration**: ENV to DB migration scenarios
- **TestValidation**: Setting value validation
- **TestBulkOperations**: Bulk updates and operations
- **TestResetSettings**: Reset to defaults
- **TestBackwardCompatibility**: ENV-only mode support
- **TestIntegrationSettings**: Integration-specific settings

### conftest.py

Shared fixtures available across all tests:

- `test_encryption_key`: Session-scoped encryption key
- `temp_env`: Temporary environment variables
- `clean_temp_db`: Fresh test database for each test
- `test_db_path`: Path to test database

## Test Fixtures

Common fixtures from `test_settings_migration.py`:

- `temp_db`: Temporary database manager
- `encryption_service`: Encryption service with test key
- `settings_repo`: Settings repository
- `credentials_repo`: Credentials repository
- `audit_repo`: Audit log repository
- `settings_service`: Complete settings service
- `test_env_vars`: Pre-configured test environment variables

## Writing New Tests

### Example Test

```python
import pytest
from src.services.settings import SettingsService


def test_my_feature(settings_service, test_env_vars):
    """Test description."""
    # Arrange
    expected_value = "test_value"

    # Act
    result = settings_service.get_config_with_fallback("my.setting")

    # Assert
    assert result == expected_value
```

### Using Markers

```python
@pytest.mark.integration
def test_external_service():
    """Test that requires external service."""
    pass


@pytest.mark.slow
def test_performance():
    """Test that takes a long time."""
    pass


@pytest.mark.migration
def test_migration_feature():
    """Test related to migration."""
    pass
```

## Continuous Integration

Tests are automatically run in CI/CD pipelines. Ensure all tests pass before committing:

```bash
# Run tests before committing
pytest

# Run with coverage check (fail if below 80%)
pytest --cov=src --cov-fail-under=80
```

## Debugging Tests

### Verbose Output

```bash
# Show print statements and detailed output
pytest -v -s

# Show local variables on failure
pytest -l

# Drop into debugger on failure
pytest --pdb
```

### Logging

```bash
# Show log output
pytest --log-cli-level=DEBUG

# Capture logs to file
pytest --log-file=test.log --log-file-level=DEBUG
```

## Test Database

Tests use temporary SQLite databases that are created and destroyed for each test. No cleanup is required.

## Best Practices

1. **Isolation**: Each test should be independent and not rely on other tests
2. **Fixtures**: Use fixtures for common setup to avoid duplication
3. **Descriptive Names**: Test names should clearly describe what they test
4. **Arrange-Act-Assert**: Structure tests with clear setup, execution, and verification
5. **Mock External Services**: Don't rely on external APIs in tests
6. **Fast Tests**: Keep tests fast to encourage frequent running

## Troubleshooting

### Import Errors

If you see import errors, ensure the package is installed in development mode:

```bash
pip install -e .
```

### Database Errors

If tests fail with database errors, ensure migrations are up to date:

```bash
python -m src.core.database
```

### Encryption Errors

If encryption tests fail, verify cryptography package is installed:

```bash
pip install cryptography
```

## Contributing

When adding new features:

1. Write tests first (TDD approach recommended)
2. Ensure all tests pass: `pytest`
3. Check coverage: `pytest --cov=src --cov-report=term-missing`
4. Run linting: `ruff check src tests`
5. Format code: `black src tests`

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
