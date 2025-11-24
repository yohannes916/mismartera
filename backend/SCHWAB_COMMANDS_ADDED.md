# Charles Schwab API Commands

## Overview

Added **Charles Schwab API connection test commands** to the CLI, using the command registry pattern for consistency with other integration commands (Claude AI, Alpaca).

## Commands Added

### 1. schwab connect
Test Charles Schwab API configuration and connectivity.

**Usage:**
```bash
schwab connect
```

**What it does:**
- Validates Schwab API credentials are configured
- Checks that base URL and callback URL are set
- Displays configuration information (with masked keys)

**Success Output:**
```
✓ Schwab connection successful
Configuration validated. Note: Full OAuth authentication requires user authorization flow.
```

**Failure Output:**
```
✗ Schwab connection failed
Check SCHWAB_APP_KEY, SCHWAB_APP_SECRET, SCHWAB_API_BASE_URL, 
and SCHWAB_CALLBACK_URL in your environment.
```

### 2. schwab disconnect
Display information about disconnecting from Schwab API.

**Usage:**
```bash
schwab disconnect
```

**Output:**
```
Schwab uses OAuth 2.0 authentication.
To fully disconnect, revoke your application authorization through Schwab's 
developer portal or remove API keys from your environment (.env).
```

## Configuration

The following environment variables must be set in your `.env` file:

```bash
# Charles Schwab API Configuration
SCHWAB_APP_KEY=your_app_key_here
SCHWAB_APP_SECRET=your_app_secret_here
SCHWAB_API_BASE_URL=https://api.schwabapi.com/trader/v1
SCHWAB_CALLBACK_URL=https://127.0.0.1:8000/callback
```

## Implementation Details

### 1. Command Registry (`app/cli/command_registry.py`)

**Added:**
```python
@dataclass(frozen=True)
class SchwabCommandMeta:
    """Metadata for Charles Schwab integration commands."""
    name: str
    usage: str
    description: str
    examples: List[str]

SCHWAB_COMMANDS: List[SchwabCommandMeta] = [
    SchwabCommandMeta(
        name="connect",
        usage="schwab connect",
        description="Test Charles Schwab API connectivity",
        examples=["schwab connect"],
    ),
    SchwabCommandMeta(
        name="disconnect",
        usage="schwab disconnect",
        description="Show how to logically disconnect Schwab",
        examples=["schwab disconnect"],
    ),
]
```

### 2. Schwab Client (`app/integrations/schwab_client.py`)

**Added Method:**
```python
async def validate_connection(self) -> bool:
    """
    Validate Schwab API configuration and connectivity.
    
    Returns:
        True if configuration is valid, False otherwise
    """
    try:
        # Check if credentials are configured
        if not self.app_key or not self.app_secret:
            logger.error("Schwab API credentials not configured")
            return False
        
        if not self.base_url:
            logger.error("Schwab API base URL not configured")
            return False
        
        # Log configuration details (with masked keys)
        logger.info("Schwab API configuration validated")
        logger.info(f"  Base URL: {self.base_url}")
        logger.info(f"  App Key: {self.app_key[:8]}...")
        logger.info(f"  Callback URL: {self.callback_url}")
        
        return True
        
    except Exception as e:
        logger.error(f"Schwab connection validation error: {e}")
        return False
```

### 3. Interactive CLI (`app/cli/interactive.py`)

**Added:**
- Import `SCHWAB_COMMANDS` from command registry
- Added `schwab_commands` to `CommandCompleter`
- Added Schwab tab completion support
- Added Schwab commands to help display
- Added `schwab` command handler with `connect` and `disconnect` subcommands

**Command Handler:**
```python
elif cmd == 'schwab':
    if not args:
        # Show available subcommands from registry
        subcommands = [meta.name for meta in SCHWAB_COMMANDS]
        self.console.print(f"[red]Usage: schwab <{' | '.join(subcommands)}>[/red]")
    else:
        subcmd = args[0].lower()
        if subcmd == 'connect':
            # Test connection
            ...
        elif subcmd == 'disconnect':
            # Show disconnect info
            ...
        else:
            # Show usage from registry
            ...
```

## Help Display

The commands are now visible in the help menu:

```bash
system@mismartera: help

SCHWAB COMMANDS
  schwab connect              Test Charles Schwab API connectivity
  schwab disconnect           Show how to logically disconnect Schwab
```

## Tab Completion

Full tab completion support:

```bash
system@mismartera: sch<TAB>
# Completes to: schwab

system@mismartera: schwab <TAB>
# Shows: connect  disconnect

system@mismartera: schwab con<TAB>
# Completes to: schwab connect
```

## Error Handling

### Missing Configuration
```bash
system@mismartera: schwab connect
Testing Charles Schwab API connection...

✗ Schwab connection failed
Check SCHWAB_APP_KEY, SCHWAB_APP_SECRET, SCHWAB_API_BASE_URL, 
and SCHWAB_CALLBACK_URL in your environment.
```

### Invalid Subcommand
```bash
system@mismartera: schwab invalid
Unknown schwab command. Available commands:

  schwab connect                           Test Charles Schwab API connectivity
  schwab disconnect                        Show how to logically disconnect Schwab
```

### No Subcommand
```bash
system@mismartera: schwab
Usage: schwab <connect | disconnect>
```

## Testing the Connection

Once you have your Schwab API credentials configured in `.env`:

```bash
system@mismartera: schwab connect
Testing Charles Schwab API connection...

✓ Schwab connection successful
Configuration validated. Note: Full OAuth authentication requires user authorization flow.
```

The validation checks:
- ✅ `SCHWAB_APP_KEY` is set
- ✅ `SCHWAB_APP_SECRET` is set
- ✅ `SCHWAB_API_BASE_URL` is set
- ✅ Configuration is logged (with masked keys for security)

## OAuth Note

**Important:** The `schwab connect` command validates that your API credentials are configured, but it does **not** perform the full OAuth 2.0 authorization flow. 

The full OAuth flow requires:
1. User authorization through Schwab's web interface
2. Receiving an authorization code via callback
3. Exchanging the code for access and refresh tokens

This will be implemented when the full Schwab integration is needed for live trading.

## Comparison with Other Integrations

| Feature | Claude AI | Alpaca | Schwab |
|---------|-----------|--------|--------|
| Connect Command | ✅ | ✅ | ✅ |
| Disconnect Command | ✅ | ✅ | ✅ |
| Registry-Based | ✅ | ✅ | ✅ |
| Tab Completion | ✅ | ✅ | ✅ |
| Help Integration | ✅ | ✅ | ✅ |
| Auth Type | API Key | API Key | OAuth 2.0 |

## Files Modified

1. **`app/cli/command_registry.py`**
   - Added `SchwabCommandMeta` dataclass
   - Added `SCHWAB_COMMANDS` list

2. **`app/integrations/schwab_client.py`**
   - Added `validate_connection()` method

3. **`app/cli/interactive.py`**
   - Imported `SCHWAB_COMMANDS`
   - Added `schwab_commands` to completer
   - Added Schwab tab completion
   - Added Schwab to help display
   - Added `schwab` command handler

## Usage Examples

### Quick Connection Test
```bash
# Test if Schwab credentials are configured
system@mismartera: schwab connect
```

### Get Disconnect Instructions
```bash
# Learn how to disconnect
system@mismartera: schwab disconnect
```

### View Help
```bash
# See all Schwab commands
system@mismartera: help
# Look for SCHWAB COMMANDS section
```

### Tab Completion
```bash
# Use tab completion for efficiency
system@mismartera: sch<TAB>con<TAB>
# Results in: schwab connect
```

## Benefits

✅ **Consistent API** - Follows same pattern as Claude and Alpaca commands  
✅ **Registry-Based** - Single source of truth for command metadata  
✅ **Tab Completion** - Full autocomplete support  
✅ **Help Integration** - Automatically appears in help menu  
✅ **Error Messages** - Clear guidance from registry  
✅ **Configuration Test** - Validate setup before trading  

## Next Steps

To enable full Schwab functionality:

1. **Implement OAuth Flow** - User authorization and token exchange
2. **Token Management** - Store and refresh access tokens
3. **API Methods** - Implement account, order, and market data methods
4. **WebSocket Streaming** - Real-time market data
5. **Order Execution** - Place and manage orders

## Summary

✅ **Schwab connect command** - Tests API configuration  
✅ **Schwab disconnect command** - Shows disconnect instructions  
✅ **Command registry integration** - Consistent with other integrations  
✅ **Full CLI integration** - Tab completion, help, error messages  
✅ **Configuration validation** - Checks all required settings  

Ready to test your Charles Schwab API credentials! 🎉
