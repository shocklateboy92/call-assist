# Dependency Injection Migration Guide

## Overview

This guide documents the migration from global variables and manual dependency management to FastAPI's dependency injection system for the Call Assist Broker.

## Previous Problems

### Global Variables Everywhere
```python
# Old approach - prone to initialization order issues
_broker_instance: Optional["CallAssistBroker"] = None
_db_manager_instance: Optional[DatabaseManager] = None
_broker_ref = None

def get_broker_instance() -> Optional["CallAssistBroker"]:
    return _broker_instance

def set_broker_instance(broker: "CallAssistBroker"):
    global _broker_instance
    _broker_instance = broker
```

### Manual Initialization Order
```python
# Old approach - easy to get wrong
set_database_path(db_path)
broker = CallAssistBroker()
set_broker_instance(broker)
web_server = WebUIServer(broker_ref=broker)
```

### Testing Difficulties
- Hard to mock dependencies
- Global state persists between tests
- Initialization order matters

## New Dependency Injection Solution

### Central Dependency Container
```python
# addon/broker/dependencies.py
class AppState:
    def __init__(self):
        self.database_manager: Optional[DatabaseManager] = None
        self.broker_instance = None
        self.plugin_manager: Optional[PluginManager] = None
        self._initialized = False
    
    async def initialize(self, db_path: str = "broker_data.db"):
        """Initialize all dependencies in the correct order"""
        # Database first
        self.database_manager = DatabaseManager(db_path)
        await self.database_manager.initialize()
        
        # Plugin manager
        self.plugin_manager = PluginManager()
        
        self._initialized = True
```

### FastAPI Dependency Functions
```python
# Dependency injection functions
async def get_database_manager(
    state: AppState = Depends(get_app_state)
) -> DatabaseManager:
    if state.database_manager is None:
        raise RuntimeError("Database manager not initialized")
    return state.database_manager

async def get_database_session(
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> AsyncGenerator[Session, None]:
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()

async def get_plugin_manager(
    state: AppState = Depends(get_app_state)
) -> PluginManager:
    if state.plugin_manager is None:
        raise RuntimeError("Plugin manager not initialized")
    return state.plugin_manager

async def get_broker_instance(
    state: AppState = Depends(get_app_state)
):
    if state.broker_instance is None:
        raise RuntimeError("Broker instance not set")
    return state.broker_instance
```

## Usage Examples

### FastAPI Route with Dependencies
```python
@app.get("/api/accounts")
async def get_accounts(
    session: Session = Depends(get_database_session),
    plugin_manager: PluginManager = Depends(get_plugin_manager)
) -> List[Account]:
    """Get all accounts with protocol validation"""
    accounts = list(session.exec(select(Account)).all())
    
    # Validate protocols are still available
    available_protocols = plugin_manager.get_available_protocols()
    valid_accounts = [
        acc for acc in accounts 
        if acc.protocol in available_protocols
    ]
    
    return valid_accounts
```

### Service Function with Dependencies
```python
async def create_account(
    account_data: dict,
    session: Session = Depends(get_database_session),
    plugin_manager: PluginManager = Depends(get_plugin_manager)
) -> Account:
    """Create new account with validation"""
    
    # Validate protocol exists
    available_protocols = plugin_manager.get_available_protocols()
    if account_data["protocol"] not in available_protocols:
        raise HTTPException(
            status_code=400,
            detail=f"Protocol {account_data['protocol']} not available"
        )
    
    # Create and save account
    account = Account(**account_data)
    session.add(account)
    session.commit()
    
    return account
```

### Testing with Dependency Injection
```python
# Easy to mock dependencies for testing
def test_create_account():
    # Create mock dependencies
    mock_session = Mock()
    mock_plugin_manager = Mock()
    mock_plugin_manager.get_available_protocols.return_value = ["matrix"]
    
    # Test the function with mocked dependencies
    account_data = {"protocol": "matrix", "account_id": "test"}
    result = await create_account(
        account_data, 
        session=mock_session, 
        plugin_manager=mock_plugin_manager
    )
    
    # Verify interactions
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
```

## Migration Strategy

### 1. Initialize Dependencies at Startup
```python
async def serve(db_path: str = "broker_data.db"):
    # Initialize all dependencies first
    await app_state.initialize(db_path)
    
    # Create broker with injected dependencies
    broker = CallAssistBroker(
        plugin_manager=app_state.plugin_manager,
        database_manager=app_state.database_manager
    )
    app_state.set_broker_instance(broker)
    
    # Web server now uses DI
    web_server = WebUIServer()
```

### 2. Update Route Handlers
```python
# Old way
@app.get("/ui/status")
async def status_page():
    if _broker_ref:
        status = get_status_from_broker(_broker_ref)
    else:
        status = {"error": "No broker"}

# New way
@app.get("/ui/status")
async def status_page(
    broker = Depends(get_broker_instance),
    plugin_manager: PluginManager = Depends(get_plugin_manager)
):
    status = {
        "protocols": plugin_manager.get_available_protocols(),
        "call_stations": len(broker.call_stations)
    }
```

### 3. Database Operations
```python
# Old way
async def save_account(account: Account):
    db_manager = await get_database_instance()
    with db_manager.get_session() as session:
        session.add(account)
        session.commit()

# New way - function can be used directly in FastAPI routes
async def save_account(
    account: Account,
    session: Session = Depends(get_database_session)
) -> Account:
    session.add(account)
    session.commit()
    session.refresh(account)
    return account
```

## Benefits

### 1. **Clear Dependencies**
- Function signatures show exactly what dependencies are needed
- No hidden global state
- IDE can provide better autocomplete and type checking

### 2. **Easy Testing**
- Mock any dependency by passing it as a parameter
- No global state to clean up between tests
- Each test is isolated

### 3. **Proper Lifecycle Management**
- FastAPI automatically manages database sessions
- Resources are properly closed
- No memory leaks from unclosed connections

### 4. **Type Safety**
- Full type hints for all dependencies
- mypy can catch dependency issues at static analysis time
- Better error messages when dependencies are missing

### 5. **Flexibility**
- Easy to swap implementations (e.g., different database for testing)
- Can compose dependencies in different ways
- Middleware can modify dependencies

## Backward Compatibility

During migration, the old global functions are kept for backward compatibility:

```python
# addon/broker/dependencies.py
def set_database_path(path: str):
    """Set database path (for backward compatibility)"""
    app_state.db_path = path

async def get_database_instance() -> DatabaseManager:
    """Get database instance (for backward compatibility)"""
    if app_state.database_manager is None:
        await app_state.initialize(app_state.db_path)
    return app_state.database_manager
```

This allows for gradual migration - new code uses DI, old code continues to work.

## Next Steps

1. **Migrate remaining routes** to use dependency injection
2. **Update tests** to use dependency injection for cleaner test setup
3. **Remove global variables** once all code is migrated
4. **Add more dependency types** as needed (configuration, external services, etc.)

The dependency injection approach provides a much more maintainable, testable, and scalable architecture for the broker.
