"""
Initialize default users in the database
Run this script to create default admin and trader users
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.database import AsyncSessionLocal
from app.repositories.user_repository import UserRepository
from app.services.auth.auth_service import auth_service
from app.logger import logger
from app.config import settings


async def create_default_users():
    """Create default admin and trader users"""
    async with AsyncSessionLocal() as session:
        try:
            # Check if admin user exists
            admin = await UserRepository.get_user_by_username(session, "admin")
            if not admin:
                # Create admin user with simple password
                admin_password = "admin123"
                admin_hash = auth_service.hash_password(admin_password)
                
                admin = await UserRepository.create_user(
                    session=session,
                    username="admin",
                    email="admin@mismartera.com",
                    password_hash=admin_hash,
                    role="admin"
                )
                logger.success(f"Admin user created - Password: {admin_password}")
                print(f"\n✓ Admin user created")
                print(f"  Username: admin")
                print(f"  Password: {admin_password}")
                print(f"  Email: admin@mismartera.com")
            else:
                logger.info("Admin user already exists")
                print("\n✓ Admin user already exists")
            
            # Check if demo trader exists
            trader = await UserRepository.get_user_by_username(session, "trader")
            if not trader:
                # Create demo trader
                trader_password = "demo123"
                trader_hash = auth_service.hash_password(trader_password)
                
                trader = await UserRepository.create_user(
                    session=session,
                    username="trader",
                    email="trader@mismartera.com",
                    password_hash=trader_hash,
                    role="trader"
                )
                logger.success("Demo trader user created")
                print(f"\n✓ Demo trader user created")
                print(f"  Username: trader")
                print(f"  Password: {trader_password}")
                print(f"  Email: trader@mismartera.com")
            else:
                logger.info("Demo trader user already exists")
                print("\n✓ Demo trader user already exists")
            
            # Count total users
            total_users = await UserRepository.count_users(session)
            print(f"\n📊 Total users in database: {total_users}\n")
            
        except Exception as e:
            logger.error(f"Error creating default users: {e}")
            print(f"\n❌ Error: {e}\n")
            raise


async def main():
    """Main function"""
    print("\n" + "="*50)
    print("  MisMartera - Initialize Default Users")
    print("="*50 + "\n")
    
    await create_default_users()
    
    print("="*50)
    print("  Initialization Complete!")
    print("="*50 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
