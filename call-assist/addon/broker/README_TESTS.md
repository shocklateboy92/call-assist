# Call Assist Integration Tests

This directory contains comprehensive integration tests for the Call Assist broker and matrix plugin system. The tests verify the complete flow from broker configuration through plugin initialization to actual call handling.

## Test Structure

### 📁 Test Files

- **`test_integration.py`** - Core integration tests with mock plugins
- **`test_matrix_plugin.py`** - Matrix plugin integration tests with real Matrix homeserver
- **`test_performance.py`** - Performance and stress tests

### 🧪 Test Categories

#### Integration Tests (`TestBrokerIntegration`)
- Plugin discovery and configuration
- Credential management and validation
- Call lifecycle (initiation, management, termination)
- System capabilities querying
- Error handling and edge cases

#### User Scenarios (`TestUserScenarios`)
- **Doorbell Scenario**: Visitor calls homeowner through doorbell camera
- **Security Monitoring**: Multiple cameras streaming to security room
- **Family Communication**: Kitchen-to-bedroom intercom system

#### Performance Tests (`TestPerformance`)
- Rapid call creation/termination (50 calls in <100ms)
- Concurrent call handling (100+ simultaneous calls)
- Configuration update performance
- Memory leak detection

#### Stress Tests (`TestStressConditions`)
- Plugin failure recovery
- Network latency simulation
- Configuration change stress testing

## 🚀 Running Tests

### Quick Start
```bash
# Run basic integration tests only
./run_integration_tests.sh

# Run all tests including Matrix plugin integration
./run_all_tests.sh --with-matrix

# Run performance tests
./run_all_tests.sh --performance

# Run everything
./run_all_tests.sh --full
```

### Individual Test Commands
```bash
# Specific test categories
python -m pytest test_integration.py -v                    # Integration tests
python -m pytest test_integration.py::TestUserScenarios -v # User scenarios
python -m pytest test_performance.py -m slow -v           # Performance tests

# Specific test cases
python -m pytest test_integration.py::TestBrokerIntegration::test_call_initiation_full_flow -v
python -m pytest test_integration.py::TestUserScenarios::test_doorbell_scenario -v
```

### Test Markers
```bash
# Run only integration tests
python -m pytest -m integration

# Skip slow tests
python -m pytest -m "not slow"

# Run only performance tests
python -m pytest -m slow
```

## 🛠 Test Infrastructure

### Mock Matrix Plugin
The integration tests use a sophisticated mock Matrix plugin that:
- ✅ Implements full gRPC CallPlugin interface
- ✅ Simulates credential validation
- ✅ Tracks active calls and state
- ✅ Provides realistic response times
- ✅ Supports health checks and capabilities

### Fixtures
- **`temp_plugin_dir`** - Creates temporary plugin directory with metadata
- **`mock_matrix_plugin`** - Starts mock plugin gRPC server
- **`broker_with_mock_plugin`** - Broker configured with mock plugin
- **`matrix_test_users`** - Real Matrix users for plugin tests
- **`matrix_test_room`** - Real Matrix room for testing

### Performance Metrics
The performance tests collect detailed metrics:
- Call initiation times (avg, median, min, max)
- Call termination times
- Concurrent call capacity
- Success/failure rates
- Memory usage tracking

## 📊 Test Coverage

### Broker Functionality ✅
- [x] Plugin discovery and loading
- [x] Configuration management
- [x] Credential handling
- [x] Call lifecycle management
- [x] Multiple concurrent calls
- [x] System capabilities
- [x] Error handling

### Matrix Plugin Integration ✅
- [x] Plugin initialization
- [x] Credential validation
- [x] Call start/end operations
- [x] Health monitoring
- [x] Capability reporting

### User Scenarios ✅
- [x] Doorbell video calls
- [x] Security monitoring
- [x] Family intercom
- [x] Multiple camera streams
- [x] Room-to-room calling

### Performance & Reliability ✅
- [x] Rapid call creation (50 calls/50ms)
- [x] Concurrent handling (100+ calls)
- [x] Memory leak detection
- [x] Plugin failure recovery
- [x] Network latency tolerance

## 🔧 Requirements

### Dependencies
```bash
pip install -r test_requirements.txt
```

Key testing libraries:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-grpc` - gRPC testing utilities
- `grpcio-testing` - gRPC test utilities
- `aioresponses` - HTTP mocking for Matrix tests

### Environment Setup
```bash
# Build protobuf files
../scripts/build-proto.sh

# Install broker dependencies
pip install -r requirements.txt

# For Matrix plugin tests (optional)
docker-compose -f ../../docker-compose.dev.yml up -d synapse
```

## 🎯 Test Results Example

```
=== Integration Test Results ===
✅ test_broker_startup_and_plugin_discovery
✅ test_configuration_update  
✅ test_credentials_update_and_plugin_initialization
✅ test_call_initiation_full_flow
✅ test_call_termination
✅ test_multiple_concurrent_calls
✅ test_system_capabilities_query
✅ test_invalid_credentials_handling
✅ test_call_to_nonexistent_plugin

=== User Scenarios ===
✅ test_doorbell_scenario
✅ test_security_monitoring_scenario  
✅ test_family_communication_scenario

=== Performance Results ===
📊 Rapid Call Test:
  - Calls created: 50
  - Success rate: 100.00%
  - Avg call start time: 0.001s
  - Avg call end time: 0.000s

📊 Concurrent Call Test:
  - Target concurrent calls: 100
  - Successfully created: 100
  - Active in broker: 100
```

## 🐛 Debugging Tests

### Verbose Logging
```bash
pytest test_integration.py -v -s --log-cli-level=DEBUG
```

### Inspect Test State
```bash
# Run specific test with detailed output
pytest test_integration.py::TestBrokerIntegration::test_call_initiation_full_flow -v -s --tb=long
```

### Mock Plugin Debugging
The mock plugin logs all gRPC calls and maintains state that can be inspected:
```python
# In test code
assert len(mock_matrix_plugin.active_calls) == 1
assert mock_matrix_plugin.initialized is True
assert 'access_token' in mock_matrix_plugin.credentials
```

## 🔄 Continuous Integration

These tests are designed for CI/CD environments:

### CI Configuration
```yaml
# Example GitHub Actions
- name: Run Integration Tests
  run: |
    cd call-assist/addon/broker
    pip install -r test_requirements.txt
    ./run_integration_tests.sh

- name: Run Performance Tests  
  run: |
    cd call-assist/addon/broker
    ./run_all_tests.sh --performance
```

### Test Timeouts
- Integration tests: ~2 minutes
- Performance tests: ~5 minutes  
- Full suite with Matrix: ~10 minutes

## 🎉 Contributing

### Adding New Tests
1. Follow the existing test structure
2. Use appropriate fixtures (`broker_with_mock_plugin`, etc.)
3. Add performance assertions for new scenarios
4. Include both success and failure cases
5. Update this README with new test descriptions

### Test Guidelines
- ✅ Use descriptive test names
- ✅ Include both positive and negative test cases
- ✅ Mock external dependencies appropriately
- ✅ Assert on both functionality and performance
- ✅ Clean up resources in test teardown
