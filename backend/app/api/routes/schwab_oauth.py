"""
Schwab OAuth callback endpoint
"""
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import HTMLResponse
from app.integrations.schwab_client import schwab_client
from app.logger import logger

router = APIRouter(prefix="", tags=["Schwab OAuth"])


@router.get("/callback")
async def schwab_oauth_callback(
    code: str = Query(..., description="Authorization code from Schwab"),
    session: str = Query(None, description="Session identifier")
):
    """
    OAuth 2.0 callback endpoint for Schwab authorization.
    
    This endpoint is called by Schwab after user authorizes the application.
    It exchanges the authorization code for an access token.
    """
    try:
        logger.info(f"Received OAuth callback with code: {code[:10]}...")
        
        # Exchange code for token
        token_data = await schwab_client.exchange_code_for_token(code)
        
        # Return success page
        return HTMLResponse(content=f"""
<!DOCTYPE html>
<html>
<head>
    <title>Schwab Authorization Successful</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .container {{
            background: white;
            padding: 3rem;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 500px;
        }}
        .success-icon {{
            font-size: 4rem;
            color: #10b981;
            margin-bottom: 1rem;
        }}
        h1 {{
            color: #1f2937;
            margin-bottom: 0.5rem;
        }}
        p {{
            color: #6b7280;
            margin-bottom: 1.5rem;
        }}
        .token-info {{
            background: #f3f4f6;
            padding: 1rem;
            border-radius: 8px;
            margin-top: 1.5rem;
            font-size: 0.875rem;
            text-align: left;
        }}
        .token-info strong {{
            color: #374151;
        }}
        .close-message {{
            margin-top: 2rem;
            color: #9ca3af;
            font-size: 0.875rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✓</div>
        <h1>Authorization Successful!</h1>
        <p>Your Schwab account has been successfully connected to Mismartera.</p>
        
        <div class="token-info">
            <strong>Access Token:</strong> {token_data.get('access_token', '')[:20]}...<br>
            <strong>Expires In:</strong> {token_data.get('expires_in', 0)} seconds
        </div>
        
        <p class="close-message">You can close this window and return to the CLI.</p>
    </div>
</body>
</html>
        """, status_code=200)
        
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        
        # Return error page
        return HTMLResponse(content=f"""
<!DOCTYPE html>
<html>
<head>
    <title>Schwab Authorization Failed</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }}
        .container {{
            background: white;
            padding: 3rem;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 500px;
        }}
        .error-icon {{
            font-size: 4rem;
            color: #ef4444;
            margin-bottom: 1rem;
        }}
        h1 {{
            color: #1f2937;
            margin-bottom: 0.5rem;
        }}
        p {{
            color: #6b7280;
            margin-bottom: 1.5rem;
        }}
        .error-details {{
            background: #fef2f2;
            border: 1px solid #fecaca;
            padding: 1rem;
            border-radius: 8px;
            margin-top: 1.5rem;
            font-size: 0.875rem;
            text-align: left;
            color: #991b1b;
        }}
        .retry-message {{
            margin-top: 2rem;
            color: #6b7280;
            font-size: 0.875rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error-icon">✗</div>
        <h1>Authorization Failed</h1>
        <p>There was an error connecting your Schwab account.</p>
        
        <div class="error-details">
            <strong>Error:</strong> {str(e)}
        </div>
        
        <p class="retry-message">
            Please try again from the CLI with: <code>schwab auth-start</code>
        </p>
    </div>
</body>
</html>
        """, status_code=500)
