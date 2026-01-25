# Documentation Style

Documentation should be concise and use Markdown format. Follow these guidelines:

Describe the WHAT and WHERE in a rather minimalistic style. Touch the WHY when there are important design decisions.
In general, do *not*:
- cite code - users can reference the repository on their own
- summarize benefits for general principles
- include justifications for following best practices or common principles
- Never include documentation for things that are not the concern of the particular script or module.
- Try to be compact and avoid structuring the text into sections unless it becomes too long.
- when describing files, use a table format like this

| Path          | Description                                           |
|---------------|-------------------------------------------------------|
|tests/unit/    | some description text                                 |
└── file1       | some description text                                 |
|web/ainer_web/ | some description text                                 |
└── file2       | some description text                                 |
└── file3       | some description text                                 |

In the following example (in between --- lines) I am using <del></del> tags to denote where the text is too verbose and can be deleted,
or <replace></replace><with></with> tags to denote where the text is too verbose and can be replaced with a more concise version.
also, there are <!-- --> tags to comment on teh text.

---
### Django and Database Configuration

<del>#### Overview</>

<del>The Ainer project uses a simplified database configuration with two databases:
<replace>1. **Single Development Database**: `data/db.sqlite3` - Main Django database for development
2. **In-Memory Test Database**: `:memory:` - Temporary database for unit testing
</del>
</replace><with>
| Path                       | Description                                           | Settings                                 |
|----------------------------|-------------------------------------------------------|------------------------------------------|
|data/db.sqlite3    | Django database for development                       | web/ainer_web/ainer_web/settings.py      |
|:memory:                    | Temporary database for unit testing                   | web/ainer_web/ainer_web/test_settings.py |
</with>
<!-- Precision: It is not the "Main Django database for development" but rather the only database used for development!-->

<del>This setup eliminates complexity while providing proper isolation between development and testing.</del>

#### Database Configuration Structure

**Main Django Settings** (`web/ainer_web/ainer_web/settings.py`):
```python
# Main development database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',  # Points to data/db.sqlite3
    }
}
```

**Test Settings** (`web/ainer_web/ainer_web/test_settings.py`):
```python
from .settings import *  # Inherit all main settings

# Override database for testing isolation
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # In-memory database for speed and isolation
    }
}
```

#### Settings Selection Mechanism

The project uses Django's standard `DJANGO_SETTINGS_MODULE` environment variable:
```python
# Default setting in init_env.sh
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ainer_web.settings')
```

- **Development**: Uses `ainer_web.settings` → `data/db.sqlite3`
- **Testing**: pytest-django automatically handles test database isolation
<del>

#### Database Structure Validation

The project includes persistent database structure validation using environment variables:

**Environment Configuration** (`.env`):
```bash
# Path to the single development database used for structure validation in tests
PERSISTENT_DB_PATH=data/db.sqlite3
```

**Purpose**: Validates that the development database has proper Django schema during unit tests
**Benefits**: 
- Catches missing migrations
- Verifies expected table structure  
- Ensures development database is properly initialized

#### Database Files

Current database structure:
```
web/ainer_web/
└── db.sqlite3                    # Single development database (Django managed)

tests/data/
└── unit_test.db                  # Specific unit test database (legacy)
```

**Database Contents**:
- Django core tables: `django_migrations`, `django_session`, `auth_user`, etc.
- Training app tables: `training_question`, `training_userdisciplineprofile`, etc.
- All migrated schema and application data

#### Key Benefits

1. **Simplicity**: Only two databases instead of multiple scattered files
2. **Consistency**: Single source of truth for development database
3. **Performance**: In-memory testing for speed
4. **Validation**: Persistent database validation ensures proper setup
5. **Maintainability**: Clear separation between development and testing
6. **Standard Compliance**: Follows Django best practices
</del>
<!-- This section is too verbose and can be deleted. The key benefits are already clear from the concise description above. 
The PERSISTENT_DB_PATH is OK, but I think it can be removed in a future refactoring.--> 

---
