# SystemManager Architecture

## Overview

SystemManager is the central coordinator that manages all application subsystems. It implements a **singleton registry pattern** combined with **dependency injection** to ensure all managers can communicate with each other.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                  SystemManager                      │
│                   (Singleton)                       │
│                                                     │
│  Creates and coordinates all managers:             │
│  ├── DataManager                                   │
│  ├── ExecutionManager                              │
│  └── AnalysisEngine                                │
│                                                     │
│  Each manager receives reference to SystemManager  │
└─────────────────────────────────────────────────────┘
         │                  │                │
         ▼                  ▼                ▼
   ┌──────────┐      ┌──────────────┐  ┌──────────────┐
   │   Data   │      │  Execution   │  │  Analysis    │
   │ Manager  │      │   Manager    │  │   Engine     │
   │          │      │              │  │              │
   │ system_  │      │ system_      │  │ system_      │
   │ manager  │      │ manager      │  │ manager      │
   └──────────┘      └──────────────┘  └──────────────┘
         │                  │                │
         └──────────────────┴────────────────┘
                          │
                  Can access each other via
                    SystemManager reference
```

## Key Principles

### 1. **Single Source of Truth**
- SystemManager is the **only** place that creates manager instances
- All managers are singletons that live for the application lifetime
- No manager should create another manager directly

### 2. **Dependency Injection**
- SystemManager passes itself as a reference to each manager it creates
- Managers store `self.system_manager` reference
- Managers can access other managers via `self.system_manager.get_xxx_manager()`

### 3. **Lazy Loading**
- Managers are created on first access
- No unnecessary initialization of unused subsystems

### 4. **Inter-Manager Communication**
- Managers don't import each other directly
- All cross-manager access goes through SystemManager
- Avoids circular dependencies

## Usage Examples

### Basic Usage

```python
from app.managers import get_system_manager

# Get the SystemManager
system_mgr = get_system_manager()

# Get any manager through SystemManager
data_mgr = system_mgr.get_data_manager()
exec_mgr = system_mgr.get_execution_manager()
analysis = system_mgr.get_analysis_engine()
```

### In CLI Commands

```python
def get_data_manager() -> DataManager:
    """Get DataManager via SystemManager."""
    from app.managers.system_manager import get_system_manager
    system_mgr = get_system_manager()
    return system_mgr.get_data_manager()

# Use in commands
async def some_command():
    dm = get_data_manager()
    # dm has reference to SystemManager
    # dm can access other managers if needed
```

### Manager-to-Manager Communication

```python
class DataManager:
    def __init__(self, system_manager=None):
        self.system_manager = system_manager
    
    def some_method(self):
        # Access another manager
        exec_mgr = self.get_execution_manager()
        if exec_mgr:
            exec_mgr.place_order(...)
    
    def get_execution_manager(self):
        """Get ExecutionManager via SystemManager."""
        if self.system_manager is None:
            logger.warning("SystemManager not available")
            return None
        return self.system_manager.get_execution_manager()
```

## Implementation Details

### SystemManager (`app/managers/system_manager.py`)

```python
class SystemManager:
    def __init__(self):
        self._data_manager = None
        self._execution_manager = None
        self._analysis_engine = None
    
    def get_data_manager(self):
        """Lazy-load DataManager with SystemManager reference."""
        if self._data_manager is None:
            self._data_manager = DataManager(system_manager=self)
        return self._data_manager
    
    # Similar for other managers...
```

### Manager Pattern

All managers should follow this pattern:

```python
class SomeManager:
    def __init__(self, system_manager=None):
        """
        Args:
            system_manager: Reference to SystemManager for inter-manager access
        """
        self.system_manager = system_manager
        # ... rest of initialization
    
    def get_other_manager(self):
        """Access another manager via SystemManager."""
        if self.system_manager is None:
            return None
        return self.system_manager.get_other_manager()
```

## Benefits

### ✅ **No Circular Imports**
Managers don't import each other - they access via SystemManager reference.

### ✅ **Testability**
Easy to mock SystemManager and inject test managers.

### ✅ **Single Initialization**
Each manager is guaranteed to be a singleton with one initialization.

### ✅ **Flexible**
Easy to add new managers - just add getter to SystemManager.

### ✅ **Clear Dependencies**
All manager relationships are explicit through SystemManager.

### ✅ **Lifecycle Management**
SystemManager can handle startup/shutdown in correct order.

## Current Status

### ✅ Implemented
- SystemManager singleton
- DataManager integration
- CLI using SystemManager

### 🚧 TODO
- Update ExecutionManager to accept system_manager parameter
- Update AnalysisEngine to accept system_manager parameter
- Add shutdown hooks for graceful cleanup
- Add initialization order management

## Migration Guide

### For Existing Code

**Before:**
```python
# Direct instantiation (bad)
dm = DataManager()
```

**After:**
```python
# Via SystemManager (good)
from app.managers import get_system_manager
dm = get_system_manager().get_data_manager()
```

### For New Managers

When creating a new manager:

1. Add getter method to SystemManager
2. Make manager accept `system_manager` parameter
3. Store reference: `self.system_manager = system_manager`
4. Add convenience methods to access other managers
5. Update SystemManager initialization order if needed

## Thread Safety

- SystemManager singleton creation is **not** thread-safe
- Create SystemManager at application startup before threading
- Individual managers may have their own threading considerations
- All manager access through SystemManager is safe after initialization

## Testing

```python
def test_with_system_manager():
    from app.managers import get_system_manager, reset_system_manager
    
    # Reset for clean test
    reset_system_manager()
    
    # Get fresh instance
    system_mgr = get_system_manager()
    data_mgr = system_mgr.get_data_manager()
    
    # Test...
    
    # Cleanup
    reset_system_manager()
```

## Best Practices

### ✅ DO
- Access managers via SystemManager
- Store `system_manager` reference in managers
- Use lazy loading for managers
- Add convenience methods for cross-manager access

### ❌ DON'T
- Create manager instances directly
- Import managers into other managers
- Create circular dependencies
- Store manager references directly (use SystemManager)

## Questions?

See the source code:
- `app/managers/system_manager.py` - SystemManager implementation
- `app/managers/data_manager/api.py` - Example manager integration
- `app/cli/data_commands.py` - Example CLI usage
