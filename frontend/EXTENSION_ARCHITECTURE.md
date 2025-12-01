# MisMartera VS Code Extension - Architecture & Planning

**Version:** 1.0.0  
**Date:** December 1, 2025  
**Status:** Planning Phase

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Feature Specification](#feature-specification)
4. [Security Architecture](#security-architecture)
5. [API Integration](#api-integration)
6. [Development Plan](#development-plan)
7. [Build & Deployment](#build--deployment)
8. [Testing Strategy](#testing-strategy)
9. [Maintenance & Updates](#maintenance--updates)
10. [Risk Assessment](#risk-assessment)

---

## Executive Summary

### Goal
Create a VS Code extension that serves as the primary UI and development environment for the MisMartera trading platform, enabling strategy development, system monitoring, and trade management through a unified interface.

### Key Capabilities
- **Strategy Development**: Edit Python strategies with full IDE support
- **System Control**: Start/stop system, run backtests, manage sessions
- **Market Monitoring**: View positions, orders, P&L in real-time
- **Data Visualization**: Charts for price data, performance metrics
- **Debugging**: Integrated Python debugging for strategies

### Technology Stack
- **Extension**: TypeScript (VS Code Extension API)
- **Backend**: Python FastAPI (existing)
- **UI Framework**: React (for complex webviews)
- **Charts**: Lightweight Charts (TradingView library)
- **Communication**: REST API + WebSocket

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    VS Code IDE                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         MisMartera Extension                          │  │
│  │                                                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │  │
│  │  │  UI Layer    │  │ Core Logic   │  │  Services  │  │  │
│  │  │              │  │              │  │            │  │  │
│  │  │ - Tree Views │  │ - Commands   │  │ - API      │  │  │
│  │  │ - Webviews   │  │ - State Mgmt │  │ - WebSocket│  │  │
│  │  │ - Status Bar │  │ - Events     │  │ - Auth     │  │  │
│  │  └──────────────┘  └──────────────┘  └────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│              Backend API (Python FastAPI)                    │
│  - System Manager                                            │
│  - Data Manager                                              │
│  - Execution Manager                                         │
│  - Time Manager                                              │
└─────────────────────────────────────────────────────────────┘
```

### Component Architecture

```
src/
├── extension.ts                 # Entry point, activation
├── core/
│   ├── extensionState.ts       # Global state management
│   ├── connectionManager.ts    # Backend connection lifecycle
│   └── eventBus.ts             # Internal event system
├── services/
│   ├── api/
│   │   ├── apiClient.ts        # HTTP client wrapper
│   │   ├── endpoints.ts        # API endpoint definitions
│   │   └── types.ts            # TypeScript interfaces
│   ├── websocket/
│   │   ├── wsClient.ts         # WebSocket client
│   │   └── messageHandlers.ts # WS message routing
│   └── auth/
│       ├── authProvider.ts     # Authentication flow
│       └── tokenManager.ts     # Token storage/refresh
├── views/
│   ├── sidebar/
│   │   ├── positionsView.ts    # Positions tree view
│   │   ├── ordersView.ts       # Orders tree view
│   │   ├── systemView.ts       # System status tree view
│   │   └── strategiesView.ts   # Strategies explorer
│   ├── webviews/
│   │   ├── chartPanel/         # Price charts
│   │   ├── dashboard/          # System dashboard
│   │   └── performance/        # P&L analytics
│   └── statusBar/
│       └── statusBarManager.ts # Status bar items
├── commands/
│   ├── system/
│   │   ├── startSystem.ts
│   │   ├── stopSystem.ts
│   │   └── runBacktest.ts
│   ├── data/
│   │   ├── importData.ts
│   │   └── validateSession.ts
│   └── strategy/
│       ├── createStrategy.ts
│       └── debugStrategy.ts
├── utils/
│   ├── config.ts               # Extension configuration
│   ├── logger.ts               # Logging utility
│   └── notifications.ts        # User notifications
└── types/
    └── index.ts                # Shared TypeScript types
```

---

## Feature Specification

### Phase 1: Core Infrastructure (Weeks 1-2)

#### 1.1 Connection Management
- [ ] Backend connection configuration (host, port)
- [ ] Auto-discovery of local backend
- [ ] Connection status monitoring
- [ ] Reconnection logic with exponential backoff
- [ ] Health check polling

#### 1.2 Authentication & Security
- [ ] API key/token authentication
- [ ] Secure credential storage (VS Code SecretStorage API)
- [ ] Token refresh mechanism
- [ ] Session expiration handling
- [ ] Multi-backend profile support

#### 1.3 Status Bar
- [ ] Connection indicator (connected/disconnected)
- [ ] System state (running/paused/stopped)
- [ ] Operating mode (backtest/paper/live)
- [ ] Quick actions dropdown

### Phase 2: System Control (Weeks 3-4)

#### 2.1 Command Palette Integration
- [ ] `MisMartera: Connect to Backend`
- [ ] `MisMartera: Start System`
- [ ] `MisMartera: Stop System`
- [ ] `MisMartera: Pause/Resume`
- [ ] `MisMartera: Run Backtest`
- [ ] `MisMartera: Import Market Data`
- [ ] `MisMartera: Validate Session`

#### 2.2 System View (Sidebar)
- [ ] System status tree
  - Current state
  - Uptime
  - Active sessions
  - Error count
- [ ] Quick action buttons
- [ ] Log streaming view

### Phase 3: Trading Interface (Weeks 5-7)

#### 3.1 Positions View
- [ ] Tree view of open positions
  - Symbol, quantity, avg price
  - Current price, P&L
  - Unrealized/realized P&L
- [ ] Context menu actions
  - Close position
  - View details
  - Export to CSV
- [ ] Auto-refresh on updates

#### 3.2 Orders View
- [ ] Active orders list
  - Order type, symbol, quantity
  - Limit price, status
  - Fill percentage
- [ ] Order history
- [ ] Context menu
  - Cancel order
  - Modify order
  - View execution details
- [ ] Filter/sort capabilities

#### 3.3 Strategies View
- [ ] List of available strategies
- [ ] Strategy status (active/inactive)
- [ ] Quick actions
  - Create new strategy (template)
  - Edit strategy (open file)
  - Enable/disable strategy
  - View strategy logs

### Phase 4: Data Visualization (Weeks 8-10)

#### 4.1 Price Chart Panel
- [ ] Candlestick/bar charts
- [ ] Multiple timeframes (1m, 5m, 15m, etc.)
- [ ] Volume overlay
- [ ] Technical indicators
  - Moving averages
  - Bollinger Bands
  - RSI, MACD
- [ ] Trade markers (buy/sell signals)
- [ ] Drawing tools
- [ ] Chart synchronization across symbols

#### 4.2 Performance Dashboard
- [ ] P&L chart (equity curve)
- [ ] Win rate, Sharpe ratio
- [ ] Drawdown analysis
- [ ] Trade distribution histogram
- [ ] Performance metrics table
- [ ] Time-period filters

#### 4.3 Live Data Feed
- [ ] Real-time price updates (WebSocket)
- [ ] Market depth (if available)
- [ ] Time & sales
- [ ] Streaming bar updates

### Phase 5: Strategy Development (Weeks 11-12)

#### 5.1 Strategy Templates
- [ ] Template scaffolding
  - Momentum strategy
  - Mean reversion
  - Pairs trading
- [ ] Code snippets
- [ ] Auto-import common libraries

#### 5.2 Debugging Integration
- [ ] Launch configuration for strategy debugging
- [ ] Breakpoint support
- [ ] Variable inspection
- [ ] Step through backtest execution

#### 5.3 Strategy Testing
- [ ] Run strategy on historical data
- [ ] View results inline
- [ ] Performance report generation

### Phase 6: Advanced Features (Weeks 13-16)

#### 6.1 Session Management
- [ ] Session data viewer
- [ ] Data quality validation
- [ ] Export session data to CSV
- [ ] Replay session (visualization)

#### 6.2 Notifications
- [ ] Trade execution alerts
- [ ] System errors/warnings
- [ ] Performance milestones
- [ ] Data gaps detected

#### 6.3 Settings & Configuration
- [ ] Extension settings page
  - API endpoint URL
  - Polling intervals
  - Chart preferences
  - Notification settings
- [ ] Workspace-specific settings
- [ ] Backend configuration sync

---

## Security Architecture

### 1. Authentication

#### API Key Authentication
```typescript
// authProvider.ts
interface AuthConfig {
    apiKey: string;          // Stored in SecretStorage
    apiEndpoint: string;     // User-configurable
    tokenExpiry?: number;    // Optional JWT expiry
}
```

**Flow:**
1. User enters API key in settings
2. Extension stores in VS Code SecretStorage API (encrypted)
3. Include in `Authorization: Bearer <token>` header
4. Backend validates and returns session token
5. Extension caches token until expiry

#### Security Measures
- **No plaintext storage**: All credentials in SecretStorage
- **HTTPS only**: Enforce TLS for API calls (configurable for dev)
- **Token refresh**: Automatic silent refresh before expiry
- **Session timeout**: Clear credentials on timeout
- **Rate limiting**: Respect backend rate limits

### 2. API Communication

#### REST API Security
```typescript
// apiClient.ts
class SecureApiClient {
    private async getAuthHeader(): Promise<string> {
        const token = await this.tokenManager.getToken();
        return `Bearer ${token}`;
    }
    
    async request(endpoint: string, options: RequestOptions) {
        // Always use HTTPS in production
        if (this.isProduction && !endpoint.startsWith('https://')) {
            throw new Error('HTTPS required in production');
        }
        
        // Add auth header
        options.headers = {
            ...options.headers,
            'Authorization': await this.getAuthHeader()
        };
        
        // Set timeout
        const controller = new AbortController();
        setTimeout(() => controller.abort(), 30000);
        
        return fetch(endpoint, { ...options, signal: controller.signal });
    }
}
```

#### WebSocket Security
- **WSS only** in production (encrypted WebSocket)
- **Authentication**: Send token in initial handshake
- **Heartbeat**: Detect dead connections
- **Message validation**: Validate all incoming messages

### 3. Data Protection

#### Local Storage
- **Extension State**: VS Code's globalState/workspaceState
- **Sensitive Data**: SecretStorage API only
- **Cache**: Temporary data in memory, cleared on disconnect

#### What NOT to Store
- ❌ API keys in plaintext
- ❌ Trading credentials
- ❌ Full trade history (only session summary)

### 4. Permissions

#### Required VS Code Permissions
```json
{
    "activationEvents": [
        "onView:mismartera.positions",
        "onCommand:mismartera.connect"
    ],
    "contributes": {
        "configuration": [...],
        "views": [...],
        "commands": [...]
    }
}
```

**No excessive permissions:**
- No filesystem access beyond workspace
- No network access to external sites
- No execution of arbitrary code

### 5. Audit & Logging

```typescript
// logger.ts
class SecureLogger {
    log(level: string, message: string, metadata?: any) {
        // Sanitize: remove sensitive data
        const sanitized = this.sanitize(metadata);
        
        // Log to VS Code output channel
        this.outputChannel.appendLine(
            `[${level}] ${message} ${JSON.stringify(sanitized)}`
        );
        
        // Optionally send to backend audit log
        if (this.config.auditLogging) {
            this.apiClient.sendAuditLog({ level, message, sanitized });
        }
    }
    
    private sanitize(data: any): any {
        // Remove API keys, tokens, passwords
        const sensitiveKeys = ['apiKey', 'token', 'password', 'secret'];
        // ... sanitization logic
    }
}
```

---

## API Integration

### Backend API Requirements

#### Authentication Endpoint
```
POST /api/auth/login
Request:  { "api_key": "..." }
Response: { "token": "jwt...", "expires_in": 3600 }
```

#### System Control Endpoints
```
GET  /api/system/status
POST /api/system/start
POST /api/system/stop
POST /api/system/pause
POST /api/system/resume
```

#### Trading Endpoints
```
GET  /api/positions
GET  /api/orders
GET  /api/trades
POST /api/orders         # Place order
DELETE /api/orders/:id   # Cancel order
```

#### Market Data Endpoints
```
GET  /api/data/bars?symbol=AAPL&interval=1m&start=...&end=...
GET  /api/data/session
POST /api/data/import
```

#### Strategy Endpoints
```
GET  /api/strategies
POST /api/strategies/:id/start
POST /api/strategies/:id/stop
GET  /api/strategies/:id/logs
```

#### Backtest Endpoints
```
POST /api/backtest/run
GET  /api/backtest/:id/status
GET  /api/backtest/:id/results
```

### WebSocket Events

#### Connection
```
ws://localhost:8000/ws?token=<jwt>

Client -> Server: { "type": "subscribe", "channels": ["positions", "orders"] }
Server -> Client: { "type": "subscribed", "channels": [...] }
```

#### Real-Time Updates
```javascript
// Position update
{ 
    "type": "position_update",
    "data": {
        "symbol": "AAPL",
        "quantity": 100,
        "avg_price": 150.00,
        "current_price": 151.50,
        "pnl": 150.00
    }
}

// Order filled
{
    "type": "order_filled",
    "data": {
        "order_id": "123",
        "symbol": "AAPL",
        "quantity": 50,
        "fill_price": 150.25
    }
}

// System state change
{
    "type": "system_state",
    "data": { "state": "running", "mode": "backtest" }
}

// Bar update (streaming)
{
    "type": "bar_update",
    "data": {
        "symbol": "AAPL",
        "interval": "1m",
        "timestamp": "2024-12-01T14:30:00",
        "open": 150.00,
        "high": 150.50,
        "low": 149.75,
        "close": 150.25,
        "volume": 10000
    }
}
```

### Error Handling

```typescript
interface ApiError {
    code: string;           // e.g., "AUTH_FAILED"
    message: string;        // Human-readable
    details?: any;          // Additional context
}

// Standardized error responses
{
    "error": {
        "code": "INSUFFICIENT_FUNDS",
        "message": "Not enough capital to place order",
        "details": { "required": 10000, "available": 5000 }
    }
}
```

---

## Development Plan

### Phase 1: Foundation (Weeks 1-2)

**Sprint 1.1: Project Setup**
- [ ] Create extension scaffold with `yo code`
- [ ] Set up TypeScript configuration
- [ ] Configure ESLint, Prettier
- [ ] Set up Git repository structure
- [ ] Create build pipeline (webpack)
- [ ] Write initial documentation

**Sprint 1.2: Core Infrastructure**
- [ ] Implement connection manager
- [ ] Create API client wrapper
- [ ] Build authentication flow
- [ ] Add status bar integration
- [ ] Implement basic logging

**Sprint 1.3: Testing Setup**
- [ ] Configure Jest for unit tests
- [ ] Set up VS Code extension test runner
- [ ] Write tests for core services
- [ ] Set up CI pipeline (GitHub Actions)

### Phase 2: System Control (Weeks 3-4)

**Sprint 2.1: Command Integration**
- [ ] Register all system commands
- [ ] Implement command handlers
- [ ] Add input validation
- [ ] Create confirmation dialogs
- [ ] Write command tests

**Sprint 2.2: System View**
- [ ] Create system status tree view
- [ ] Implement data provider
- [ ] Add refresh mechanism
- [ ] Style tree view items
- [ ] Add context menu actions

### Phase 3: Trading UI (Weeks 5-7)

**Sprint 3.1: Positions View**
- [ ] Design tree structure
- [ ] Implement data provider
- [ ] Add auto-refresh logic
- [ ] Create context menu
- [ ] Style with icons/colors

**Sprint 3.2: Orders View**
- [ ] Build orders tree view
- [ ] Add filter/sort functionality
- [ ] Implement order actions
- [ ] Add order history view
- [ ] Connect to WebSocket for updates

**Sprint 3.3: Strategies View**
- [ ] List strategies
- [ ] Add enable/disable actions
- [ ] Create strategy templates
- [ ] Implement strategy creation wizard

### Phase 4: Visualization (Weeks 8-10)

**Sprint 4.1: Chart Panel Setup**
- [ ] Set up React webview
- [ ] Integrate Lightweight Charts
- [ ] Implement basic candlestick chart
- [ ] Add zoom/pan controls

**Sprint 4.2: Advanced Charts**
- [ ] Add technical indicators
- [ ] Implement timeframe switching
- [ ] Add trade markers
- [ ] Create chart settings UI

**Sprint 4.3: Performance Dashboard**
- [ ] Design dashboard layout
- [ ] Implement P&L chart
- [ ] Add metrics cards
- [ ] Create report export

### Phase 5: Strategy Development (Weeks 11-12)

**Sprint 5.1: Templates & Scaffolding**
- [ ] Create strategy templates
- [ ] Build scaffolding command
- [ ] Add code snippets
- [ ] Write strategy guide

**Sprint 5.2: Debugging**
- [ ] Create launch configuration
- [ ] Test Python debugger integration
- [ ] Add strategy log viewer
- [ ] Document debugging workflow

### Phase 6: Polish & Release (Weeks 13-16)

**Sprint 6.1: Advanced Features**
- [ ] Implement notifications
- [ ] Add session management UI
- [ ] Create settings page
- [ ] Implement data export

**Sprint 6.2: Testing & Optimization**
- [ ] Comprehensive testing
- [ ] Performance optimization
- [ ] Memory leak detection
- [ ] Load testing

**Sprint 6.3: Documentation & Release**
- [ ] Write user guide
- [ ] Create video tutorials
- [ ] Package extension
- [ ] Internal release

---

## Build & Deployment

### Build Configuration

#### package.json
```json
{
    "name": "mismartera-vscode",
    "displayName": "MisMartera Trading Platform",
    "description": "Algorithmic trading development and monitoring",
    "version": "1.0.0",
    "publisher": "mismartera",
    "engines": {
        "vscode": "^1.85.0"
    },
    "categories": [
        "Other"
    ],
    "activationEvents": [
        "onView:mismartera.positions",
        "onCommand:mismartera.connect"
    ],
    "main": "./dist/extension.js",
    "contributes": {
        "configuration": {
            "title": "MisMartera",
            "properties": {
                "mismartera.apiEndpoint": {
                    "type": "string",
                    "default": "http://localhost:8000",
                    "description": "Backend API endpoint"
                },
                "mismartera.autoConnect": {
                    "type": "boolean",
                    "default": true,
                    "description": "Auto-connect on extension activation"
                }
            }
        },
        "views": {
            "mismartera": [
                {
                    "id": "mismartera.positions",
                    "name": "Positions"
                },
                {
                    "id": "mismartera.orders",
                    "name": "Orders"
                }
            ]
        },
        "commands": [
            {
                "command": "mismartera.connect",
                "title": "Connect to Backend",
                "category": "MisMartera"
            }
        ]
    },
    "scripts": {
        "vscode:prepublish": "npm run compile",
        "compile": "webpack --mode production",
        "watch": "webpack --mode development --watch",
        "test": "jest",
        "package": "vsce package",
        "deploy": "vsce publish"
    },
    "devDependencies": {
        "@types/vscode": "^1.85.0",
        "typescript": "^5.0.0",
        "webpack": "^5.0.0",
        "ts-loader": "^9.0.0",
        "@vscode/test-electron": "^2.3.0"
    },
    "dependencies": {
        "axios": "^1.6.0",
        "ws": "^8.14.0",
        "lightweight-charts": "^4.1.0"
    }
}
```

#### webpack.config.js
```javascript
const path = require('path');

module.exports = {
    target: 'node',
    entry: './src/extension.ts',
    output: {
        path: path.resolve(__dirname, 'dist'),
        filename: 'extension.js',
        libraryTarget: 'commonjs2'
    },
    externals: {
        vscode: 'commonjs vscode'
    },
    resolve: {
        extensions: ['.ts', '.js']
    },
    module: {
        rules: [
            {
                test: /\.ts$/,
                exclude: /node_modules/,
                use: 'ts-loader'
            }
        ]
    },
    devtool: 'source-map'
};
```

### Build Process

```bash
# Development
npm run watch        # Watch mode for development
F5                   # Launch Extension Development Host

# Testing
npm test            # Run unit tests
npm run test:e2e    # Run integration tests

# Production Build
npm run compile     # Compile TypeScript -> JavaScript
npm run package     # Create .vsix file

# Deployment
npm run deploy      # Publish to marketplace (optional)
```

### Packaging Strategy

#### Internal Distribution (.vsix)
```bash
# Build extension
npm run compile

# Create package
vsce package

# Result: mismartera-vscode-1.0.0.vsix

# Install
code --install-extension mismartera-vscode-1.0.0.vsix
```

#### Version Management
- **Semantic Versioning**: MAJOR.MINOR.PATCH
- **1.0.0**: Initial release
- **1.1.0**: New features
- **1.0.1**: Bug fixes

#### Release Checklist
- [ ] Update version in package.json
- [ ] Update CHANGELOG.md
- [ ] Run all tests (pass 100%)
- [ ] Build production bundle
- [ ] Test on clean VS Code install
- [ ] Create .vsix package
- [ ] Tag Git release
- [ ] Distribute .vsix file

### CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/build.yml
name: Build and Test

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup Node.js
      uses: actions/setup-node@v3
      with:
        node-version: '18'
    
    - name: Install dependencies
      run: npm ci
    
    - name: Run linter
      run: npm run lint
    
    - name: Run tests
      run: npm test
    
    - name: Build extension
      run: npm run compile
    
    - name: Package extension
      run: npm run package
    
    - name: Upload artifact
      uses: actions/upload-artifact@v3
      with:
        name: extension
        path: '*.vsix'

  release:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
    - name: Download artifact
      uses: actions/download-artifact@v3
    
    - name: Create Release
      uses: softprops/action-gh-release@v1
      with:
        files: '*.vsix'
        tag_name: v${{ github.run_number }}
```

---

## Testing Strategy

### Unit Tests (Jest)

```typescript
// src/services/api/apiClient.test.ts
import { ApiClient } from './apiClient';
import { TokenManager } from '../auth/tokenManager';

describe('ApiClient', () => {
    let client: ApiClient;
    let mockTokenManager: jest.Mocked<TokenManager>;
    
    beforeEach(() => {
        mockTokenManager = {
            getToken: jest.fn().mockResolvedValue('test-token')
        } as any;
        
        client = new ApiClient('http://localhost:8000', mockTokenManager);
    });
    
    test('should add auth header to requests', async () => {
        const mockFetch = jest.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ data: 'test' })
        });
        global.fetch = mockFetch;
        
        await client.get('/api/positions');
        
        expect(mockFetch).toHaveBeenCalledWith(
            'http://localhost:8000/api/positions',
            expect.objectContaining({
                headers: expect.objectContaining({
                    'Authorization': 'Bearer test-token'
                })
            })
        );
    });
    
    test('should handle API errors', async () => {
        global.fetch = jest.fn().mockResolvedValue({
            ok: false,
            status: 401,
            json: async () => ({ error: { code: 'UNAUTHORIZED' } })
        });
        
        await expect(client.get('/api/positions')).rejects.toThrow();
    });
});
```

### Integration Tests

```typescript
// src/views/positionsView.test.ts
import * as vscode from 'vscode';
import { PositionsView } from './positionsView';

describe('PositionsView Integration', () => {
    let extension: vscode.Extension<any>;
    
    beforeAll(async () => {
        extension = vscode.extensions.getExtension('mismartera.mismartera-vscode')!;
        await extension.activate();
    });
    
    test('should display positions in tree view', async () => {
        // Trigger view update
        await vscode.commands.executeCommand('mismartera.refreshPositions');
        
        // Verify tree items
        const treeView = extension.exports.positionsView;
        const items = await treeView.getChildren();
        
        expect(items).toHaveLength(2);
        expect(items[0].label).toBe('AAPL');
    });
});
```

### E2E Tests

```typescript
// Test with real backend
describe('E2E: Trading Workflow', () => {
    test('full workflow: connect -> view positions -> place order', async () => {
        // 1. Connect to backend
        await vscode.commands.executeCommand('mismartera.connect');
        await waitForConnection();
        
        // 2. View positions
        const positions = await getPositions();
        expect(positions).toBeDefined();
        
        // 3. Place order
        await vscode.commands.executeCommand('mismartera.placeOrder', {
            symbol: 'AAPL',
            quantity: 10,
            type: 'market'
        });
        
        // 4. Verify order appears
        await waitFor(() => {
            const orders = getOrders();
            return orders.some(o => o.symbol === 'AAPL');
        });
    });
});
```

### Test Coverage Goals
- **Unit Tests**: >80% code coverage
- **Integration Tests**: All commands and views
- **E2E Tests**: Critical user workflows
- **Performance Tests**: WebSocket message handling, chart rendering

---

## Maintenance & Updates

### Update Strategy

#### Extension Updates
- **Patch** (1.0.x): Bug fixes, shipped weekly
- **Minor** (1.x.0): New features, shipped monthly
- **Major** (x.0.0): Breaking changes, shipped yearly

#### Backward Compatibility
- Maintain compatibility with backend API for 2 major versions
- Graceful degradation if backend missing features
- Version negotiation on connection

### Monitoring

#### Error Tracking
```typescript
// Telemetry (optional, user opt-in)
class TelemetryService {
    reportError(error: Error, context: any) {
        // Send to error tracking service
        // OR log locally for debugging
    }
    
    reportUsage(command: string) {
        // Track feature usage
    }
}
```

#### Health Checks
- Monitor connection stability
- Track API response times
- Log WebSocket disconnections
- Alert on repeated errors

### User Feedback
- In-extension feedback form
- GitHub issues for bug reports
- Feature request tracking
- User surveys (optional)

---

## Risk Assessment

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Backend API changes break extension | Medium | High | Version negotiation, graceful degradation |
| WebSocket connection instability | Medium | Medium | Reconnection logic, fallback to polling |
| Performance issues with large datasets | Low | Medium | Pagination, virtual scrolling, data limits |
| VS Code API changes | Low | Medium | Target stable API, test on Insiders |
| Security vulnerabilities | Low | High | Security audit, dependency scanning |

### Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Users on outdated VS Code version | Medium | Low | Min version check, clear requirements |
| Conflicting extensions | Low | Low | Namespace commands, test with common extensions |
| Network firewall blocks WebSocket | Medium | Medium | Fallback to HTTP polling |
| Extension crashes VS Code | Low | High | Thorough testing, error boundaries |

### Business Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Low user adoption | Medium | Medium | User onboarding, documentation, demos |
| Feature creep delays release | Medium | Medium | Phased release, MVP first |
| Maintenance burden | Medium | High | Automated testing, clear architecture |

---

## Success Metrics

### Development Metrics
- [ ] 100% of Phase 1-3 features complete
- [ ] >80% test coverage
- [ ] Zero critical bugs
- [ ] <100ms UI response time

### User Metrics
- [ ] <5 minutes to first connection
- [ ] <2 clicks to view positions
- [ ] Real-time updates <1s latency
- [ ] 95% uptime (connection stability)

### Quality Metrics
- [ ] Zero data loss incidents
- [ ] <0.1% error rate
- [ ] Clean security audit
- [ ] Positive user feedback

---

## Next Steps

1. **Review & Refinement** (This document)
   - Review architecture with team
   - Identify missing requirements
   - Adjust timeline if needed

2. **Environment Setup** (Day 1)
   - Set up development environment
   - Create Git repository
   - Configure CI/CD

3. **Prototype** (Week 1)
   - Build minimal extension
   - Test connection to backend
   - Verify basic functionality

4. **Iterate** (Weeks 2-16)
   - Follow phased development plan
   - Regular testing and feedback
   - Adjust as needed

5. **Release** (Week 16)
   - Internal release
   - User testing
   - Production deployment

---

## Appendix

### Useful Resources
- [VS Code Extension API](https://code.visualstudio.com/api)
- [Extension Samples](https://github.com/microsoft/vscode-extension-samples)
- [Publishing Extensions](https://code.visualstudio.com/api/working-with-extensions/publishing-extension)
- [Lightweight Charts](https://tradingview.github.io/lightweight-charts/)

### Glossary
- **Tree View**: Hierarchical list in VS Code sidebar
- **Webview**: Custom HTML/JS UI panel
- **Command**: Action registered in command palette
- **Status Bar**: Bottom bar showing status indicators
- **SecretStorage**: Encrypted credential storage

---

**Document Version:** 1.0  
**Last Updated:** December 1, 2025  
**Authors:** AI Architecture Team  
**Status:** DRAFT - Awaiting Review
