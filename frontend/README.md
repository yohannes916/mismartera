# MisMartera Frontend - VS Code Extension

This directory contains the MisMartera trading platform VS Code extension and related frontend components.

## 📁 Directory Structure

```
frontend/
├── desktop-app/                    # Code-OSS development setup
│   ├── .node/                     # Embedded Node.js (ignored)
│   ├── setup_embedded_node.sh    # Setup script
│   └── launch_code.sh            # Launcher script
│
├── extension/                      # VS Code extension (to be created)
│   └── (Extension code will go here)
│
├── EXTENSION_ARCHITECTURE.md      # 📘 Architecture & technical design
├── EXTENSION_IMPLEMENTATION_PLAN.md  # 📋 Week-by-week implementation plan
└── README.md                       # This file
```

## 📚 Documentation

### 1. [EXTENSION_ARCHITECTURE.md](./EXTENSION_ARCHITECTURE.md)
**Comprehensive architecture and planning document**

**Contents:**
- Executive Summary
- High-level architecture
- Feature specifications (Phase 1-6)
- Security architecture
- API integration requirements
- Development phases
- Build & deployment strategy
- Testing strategy
- Risk assessment

**Use this for:**
- Understanding overall system design
- Security considerations
- API contracts
- Long-term planning

### 2. [EXTENSION_IMPLEMENTATION_PLAN.md](./EXTENSION_IMPLEMENTATION_PLAN.md)
**Tactical week-by-week implementation guide**

**Contents:**
- 16-week detailed breakdown
- Daily task lists
- Code examples and snippets
- Testing approach
- Progress tracking
- Decision log
- Success criteria

**Use this for:**
- Day-to-day development
- Sprint planning
- Task estimation
- Progress tracking

## 🎯 Quick Decision: Extension vs Core Customization

**✅ DECISION: Build a VS Code Extension (NOT core customization)**

### Why Extension?
- ✅ Easy updates (VS Code updates independently)
- ✅ Clean separation (Backend ↔ Extension ↔ VS Code)
- ✅ Simple distribution (.vsix file)
- ✅ Easy maintenance
- ✅ Standard approach

### Why NOT Core Customization?
- ❌ Update hell (merge conflicts on every VS Code update)
- ❌ Extreme complexity
- ❌ Hard to distribute
- ❌ Maintenance nightmare
- ❌ Overkill for requirements

## 🚀 Quick Start

### Option 1: Develop Extension (Recommended)
```bash
# 1. Install Yeoman and VS Code extension generator
npm install -g yo generator-code

# 2. Generate extension scaffold
cd frontend/
yo code
# Choose: New Extension (TypeScript)
# Name: mismartera-vscode

# 3. Start developing
cd mismartera-vscode/
npm install
code .
# Press F5 to launch Extension Development Host
```

### Option 2: Explore Code-OSS (Optional)
```bash
# If you want to understand VS Code internals
cd frontend/desktop-app/

# Run setup (one-time, ~15 minutes)
./setup_embedded_node.sh

# Launch Code-OSS
./launch_code.sh
```

## 🏗️ Extension Architecture Overview

```
┌──────────────────────────────────────────┐
│         VS Code + Extension              │
│  ┌────────────────────────────────────┐  │
│  │  Sidebar Views                     │  │
│  │  - Positions                       │  │
│  │  - Orders                          │  │
│  │  - System Status                   │  │
│  │  - Strategies                      │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  Webview Panels                    │  │
│  │  - Price Charts (TradingView)      │  │
│  │  - Performance Dashboard           │  │
│  │  - Session Analytics               │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  Commands & Status Bar             │  │
│  │  - Start/Stop System               │  │
│  │  - Run Backtest                    │  │
│  │  - Import Data                     │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
              ↕ REST + WebSocket
┌──────────────────────────────────────────┐
│      Backend API (Python FastAPI)        │
│  - System Manager                        │
│  - Data Manager                          │
│  - Trading Engine                        │
└──────────────────────────────────────────┘
```

## 📦 Technology Stack

### Extension
- **Language**: TypeScript
- **Framework**: VS Code Extension API
- **UI Components**: 
  - Tree Views (native)
  - Webviews (React)
- **Charts**: Lightweight Charts (TradingView)
- **HTTP**: Axios
- **WebSocket**: ws library

### Build Tools
- **Bundler**: Webpack
- **Testing**: Jest + VS Code Test Framework
- **Linting**: ESLint + Prettier
- **Package**: vsce (VS Code Extension CLI)

## 🔒 Security Highlights

### Authentication
- API key stored in VS Code SecretStorage (encrypted)
- JWT tokens for session management
- Automatic token refresh
- HTTPS enforced in production

### Data Protection
- No plaintext credential storage
- Sensitive data in memory only
- Secure WebSocket (WSS)
- Input validation on all API calls

### Permissions
- Minimal VS Code permissions
- No filesystem access beyond workspace
- No external network requests (except backend)

## 📅 Timeline

### Phase 1: Foundation (Weeks 1-4)
- Project setup
- Backend connection
- Authentication
- System control commands

### Phase 2: Trading UI (Weeks 5-8)
- Positions view
- Orders view
- Strategies view
- WebSocket integration

### Phase 3: Visualization (Weeks 9-12)
- Price charts
- Performance dashboard
- Strategy development tools

### Phase 4: Polish (Weeks 13-16)
- Session management
- Notifications
- Settings
- Testing & documentation
- Release

**Total: 16 weeks (4 months)**

## 🎯 Success Metrics

### Functional
- ✅ Connect to backend in <5 minutes
- ✅ View positions in real-time
- ✅ Execute trades via UI
- ✅ Display price charts
- ✅ Run backtests

### Performance
- ✅ <100ms UI response time
- ✅ <1s WebSocket latency
- ✅ 60 FPS chart rendering

### Quality
- ✅ >80% test coverage
- ✅ Zero critical bugs
- ✅ Clean security audit

## 🛠️ Development Workflow

### Daily
1. Plan day's tasks
2. Implement features
3. Write tests
4. Test in Extension Development Host (F5)
5. Commit & push

### Weekly
- Run full test suite
- Integration testing with backend
- Code review
- Update documentation

### Release
```bash
# Build
npm run compile
npm test

# Package
vsce package

# Install locally
code --install-extension mismartera-vscode-1.0.0.vsix
```

## 📖 Further Reading

### Official Resources
- [VS Code Extension API](https://code.visualstudio.com/api)
- [Extension Samples](https://github.com/microsoft/vscode-extension-samples)
- [Publishing Extensions](https://code.visualstudio.com/api/working-with-extensions/publishing-extension)

### Libraries
- [Lightweight Charts Docs](https://tradingview.github.io/lightweight-charts/)
- [React Docs](https://react.dev/)
- [Axios Docs](https://axios-http.com/)

## 🤝 Contributing

### Development Setup
1. Read `EXTENSION_ARCHITECTURE.md`
2. Review `EXTENSION_IMPLEMENTATION_PLAN.md`
3. Set up development environment
4. Create feature branch
5. Implement with tests
6. Submit for review

### Coding Standards
- TypeScript strict mode
- ESLint + Prettier formatting
- Test coverage >80%
- Clear commit messages
- Documentation for new features

## 📞 Support

### Internal
- Architecture questions → Review architecture doc
- Implementation questions → Check implementation plan
- Backend API → See backend documentation

### External (Future)
- GitHub Issues
- VS Code Marketplace (after public release)

---

## Next Steps

1. **Review Documentation**
   - Read `EXTENSION_ARCHITECTURE.md` thoroughly
   - Understand security requirements
   - Review API contracts

2. **Refine Plan**
   - Identify any missing features
   - Adjust timeline if needed
   - Clarify requirements

3. **Set Up Environment**
   ```bash
   npm install -g yo generator-code
   yo code
   ```

4. **Start Week 1**
   - Follow `EXTENSION_IMPLEMENTATION_PLAN.md`
   - Begin with project setup
   - Create Git repository

---

**Status:** Planning Complete ✅  
**Ready for:** Implementation  
**Next Action:** Environment setup + Week 1 tasks
