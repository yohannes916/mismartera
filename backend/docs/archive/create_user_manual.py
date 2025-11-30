"""
Manual User Creation Script (Workaround for bcrypt issue)
Use this until bcrypt compatibility is resolved
"""
import asyncio
import bcrypt
from app.models.database import AsyncSessionLocal
from app.models.user import User
from app.logger import logger


async def create_user_manually(username: str, email: str, password: str, role: str = "trader"):
    """Create a user manually with bcrypt directly"""
    async with AsyncSessionLocal() as session:
        try:
            # Hash password directly with bcrypt
            password_bytes = password.encode('utf-8')
            salt = bcrypt.gensalt()
            password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
            
            # Create user
            user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                role=role,
                is_active=True
            )
            
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            logger.success(f"User created: {username}")
            print(f"\n✓ User created successfully!")
            print(f"  Username: {username}")
            print(f"  Email: {email}")
            print(f"  Role: {role}")
            print(f"  Password: {password}\n")
            
            return user
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating user: {e}")
            print(f"\n❌ Error: {e}\n")
            raise


async def main():
    print("\n" + "="*50)
    print("  Manual User Creation")
    print("="*50 + "\n")
    
    # Create admin user
    await create_user_manually(
        username="admin",
        email="admin@mismartera.com",
        password="admin123",
        role="admin"
    )
    
    # Create demo trader
    await create_user_manually(
        username="trader",
        email="trader@mismartera.com",
        password="demo123",
        role="trader"
    )
    
    print("="*50)
    print("  Users Created Successfully!")
    print("="*50 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
