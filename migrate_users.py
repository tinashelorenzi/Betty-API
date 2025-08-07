#!/usr/bin/env python3
"""
User Migration Script for Firebase Indexing System
Place this file in the root directory (same level as main.py)
Run with: python migrate_users.py
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List
import firebase_admin
from firebase_admin import credentials, firestore
from pathlib import Path

# Add the current directory to Python path so we can import our services
sys.path.append(str(Path(__file__).parent))

class MigrationScript:
    def __init__(self):
        self.db = None
        self.initialized = False
    
    def initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            print("🔥 Initializing Firebase...")
            
            # Try to get credentials from environment or file
            firebase_cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
            
            if firebase_cred_path:
                # Handle relative paths by making them absolute
                if not os.path.isabs(firebase_cred_path):
                    firebase_cred_path = os.path.join(os.getcwd(), firebase_cred_path)
                
                if os.path.exists(firebase_cred_path):
                    print(f"📄 Using credentials file: {firebase_cred_path}")
                    cred = credentials.Certificate(firebase_cred_path)
                    firebase_admin.initialize_app(cred)
                else:
                    print(f"❌ Credentials file not found: {firebase_cred_path}")
                    sys.exit(1)
            else:
                # Try to find credentials file in credentials directory
                credentials_dir = os.path.join(os.getcwd(), "credentials")
                if os.path.exists(credentials_dir):
                    cred_files = [f for f in os.listdir(credentials_dir) if f.endswith('.json')]
                    if cred_files:
                        cred_path = os.path.join(credentials_dir, cred_files[0])
                        print(f"📄 Using credentials file: {cred_path}")
                        cred = credentials.Certificate(cred_path)
                        firebase_admin.initialize_app(cred)
                    else:
                        print("❌ No JSON credentials file found in credentials/ directory")
                        sys.exit(1)
                else:
                    print("❌ No credentials directory found")
                    sys.exit(1)
            
            self.db = firestore.client()
            self.initialized = True
            print("✅ Firebase initialized successfully!")
            
        except Exception as e:
            print(f"❌ Firebase initialization failed: {e}")
            print("\n💡 Make sure you have either:")
            print("   1. FIREBASE_CREDENTIALS_PATH environment variable set, or")
            print("   2. Firebase credentials file in the credentials/ directory")
            sys.exit(1)
    
    def get_user_document_ref(self, uid: str):
        """Get reference to user document"""
        return self.db.document(f"users/{uid}")
    
    async def query_documents(self, collection: str, filters: List = None, limit: int = None):
        """Query documents from Firestore"""
        try:
            collection_ref = self.db.collection(collection)
            query = collection_ref
            
            # Apply filters
            if filters:
                for field, operator, value in filters:
                    query = query.where(filter=firestore.FieldFilter(field, operator, value))
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            # Execute query
            docs = query.stream()
            results = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                results.append(data)
            
            return results
            
        except Exception as e:
            print(f"❌ Error querying {collection}: {e}")
            return []
    
    async def migrate_single_user(self, user_id: str) -> Dict[str, Any]:
        """Migrate a single user's data to indexed structure"""
        try:
            print(f"\n🔄 Migrating user: {user_id}")
            
            # Step 1: Check if user already has complete indexes
            user_ref = self.get_user_document_ref(user_id)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                existing_indexes = user_data.get("indexes", {})
                
                # Check if migration is complete
                if (existing_indexes.get("conversation_ids") is not None and 
                    existing_indexes.get("document_ids") is not None):
                    print(f"✅ User {user_id} already migrated, skipping...")
                    return {"status": "skipped", "reason": "already_migrated"}
            
            # Step 2: Gather all user data
            print(f"   📊 Gathering data for user {user_id}...")
            
            # Get conversations
            conversations = await self.query_documents(
                "conversations",
                filters=[("user_id", "==", user_id)]
            )
            
            # Get documents
            documents = await self.query_documents(
                "documents", 
                filters=[("user_id", "==", user_id)]
            )
            
            # Get tasks (if collection exists)
            tasks = []
            try:
                tasks = await self.query_documents(
                    "tasks",
                    filters=[("user_id", "==", user_id)]
                )
            except:
                pass  # Tasks collection might not exist
            
            # Get messages for statistics
            messages = await self.query_documents(
                "chat_history",
                filters=[("user_id", "==", user_id)]
            )
            
            print(f"   📈 Found: {len(conversations)} conversations, {len(documents)} documents, {len(tasks)} tasks, {len(messages)} messages")
            
            # Step 3: Build indexes
            conversation_ids = [conv["id"] for conv in conversations]
            document_ids = [doc["id"] for doc in documents]
            task_ids = [task["id"] for task in tasks]
            
            # Step 4: Calculate statistics
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            today_messages = []
            last_message_at = None
            
            for msg in messages:
                msg_timestamp = msg.get("timestamp")
                if msg_timestamp:
                    if isinstance(msg_timestamp, str):
                        try:
                            msg_timestamp = datetime.fromisoformat(msg_timestamp.replace('Z', '+00:00'))
                        except:
                            continue
                    
                    # Ensure both datetimes are timezone-aware for comparison
                    if msg_timestamp.tzinfo is None:
                        msg_timestamp = msg_timestamp.replace(tzinfo=timezone.utc)
                    
                    if msg_timestamp >= today_start:
                        today_messages.append(msg)
                    
                    if not last_message_at or msg_timestamp > last_message_at:
                        last_message_at = msg_timestamp
            
            # Step 5: Build the complete user data structure
            migration_data = {
                "indexes": {
                    "conversation_ids": conversation_ids,
                    "document_ids": document_ids,
                    "task_ids": task_ids,
                    "chat_session_ids": [],  # Legacy field
                    "note_ids": []  # For future use
                },
                "stats": {
                    "total_conversations": len(conversations),
                    "total_documents": len(documents),
                    "total_messages": len(messages),
                    "total_tasks": len(tasks),
                    "total_notes": 0,
                    "messages_today": len(today_messages),
                    "last_activity": datetime.now(timezone.utc),
                    "last_message_at": last_message_at
                },
                "migration_info": {
                    "migrated_at": datetime.now(timezone.utc),
                    "migration_version": "1.0",
                    "migration_script": "migrate_users.py",
                    "data_found": {
                        "conversations": len(conversations),
                        "documents": len(documents),
                        "tasks": len(tasks),
                        "messages": len(messages)
                    }
                },
                "updated_at": datetime.now(timezone.utc)
            }
            
            # Step 6: Update the user document (merge to preserve existing data)
            user_ref.set(migration_data, merge=True)
            
            print(f"✅ Successfully migrated user {user_id}")
            print(f"   📁 Indexed: {len(conversation_ids)} conversations, {len(document_ids)} documents")
            print(f"   📊 Stats: {len(messages)} total messages, {len(today_messages)} today")
            
            return {
                "status": "success",
                "data": {
                    "conversations": len(conversation_ids),
                    "documents": len(document_ids),
                    "tasks": len(task_ids),
                    "messages": len(messages)
                }
            }
            
        except Exception as e:
            print(f"❌ Failed to migrate user {user_id}: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def migrate_all_users(self):
        """Migrate all users to indexed structure"""
        try:
            print("🚀 Starting migration of all users to indexed structure...")
            
            # Get all users
            all_users = await self.query_documents("users")
            print(f"👥 Found {len(all_users)} users to process")
            
            if len(all_users) == 0:
                print("❌ No users found! Make sure your Firebase connection is correct.")
                return
            
            # Migration counters
            migrated_count = 0
            failed_count = 0
            skipped_count = 0
            migration_results = []
            
            # Process each user
            for i, user_doc in enumerate(all_users, 1):
                user_id = user_doc.get("uid") or user_doc.get("id")
                
                if not user_id:
                    print(f"⚠️ Skipping user {i} - no UID found")
                    skipped_count += 1
                    continue
                
                print(f"\n[{i}/{len(all_users)}] Processing user: {user_id}")
                
                # Migrate this user
                result = await self.migrate_single_user(user_id)
                migration_results.append({"user_id": user_id, **result})
                
                if result["status"] == "success":
                    migrated_count += 1
                elif result["status"] == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1
                
                # Small delay to be nice to Firebase
                await asyncio.sleep(0.1)
            
            # Print final summary
            print(f"\n🏁 Migration Complete!")
            print(f"{'='*50}")
            print(f"📊 SUMMARY:")
            print(f"   Total Users:     {len(all_users)}")
            print(f"   ✅ Migrated:     {migrated_count}")
            print(f"   ⏭️  Skipped:      {skipped_count}")
            print(f"   ❌ Failed:       {failed_count}")
            print(f"   📈 Success Rate: {((migrated_count + skipped_count) / len(all_users) * 100):.1f}%")
            
            # Show some sample results
            if migration_results:
                print(f"\n📝 Sample Results:")
                for result in migration_results[:5]:  # First 5
                    status_emoji = {"success": "✅", "skipped": "⏭️", "failed": "❌"}
                    emoji = status_emoji.get(result["status"], "❓")
                    print(f"   {emoji} {result['user_id']}: {result['status']}")
                
                if len(migration_results) > 5:
                    print(f"   ... and {len(migration_results) - 5} more")
            
            # Show failed migrations if any
            failed_migrations = [r for r in migration_results if r["status"] == "failed"]
            if failed_migrations:
                print(f"\n❌ Failed Migrations:")
                for failure in failed_migrations:
                    print(f"   - {failure['user_id']}: {failure.get('error', 'Unknown error')}")
            
            print(f"\n🎉 Migration script completed successfully!")
            
        except Exception as e:
            print(f"❌ Migration script failed: {e}")
            raise
    
    async def verify_migration(self):
        """Verify that the migration was successful"""
        try:
            print(f"\n🔍 Verifying migration results...")
            
            all_users = await self.query_documents("users")
            migrated_users = 0
            users_with_data = 0
            total_conversations = 0
            total_documents = 0
            total_messages = 0
            
            for user_doc in all_users:
                user_id = user_doc.get("uid") or user_doc.get("id")
                if not user_id:
                    continue
                
                indexes = user_doc.get("indexes", {})
                stats = user_doc.get("stats", {})
                
                # Check if user has been migrated
                if indexes or stats:
                    migrated_users += 1
                    
                    conv_count = len(indexes.get("conversation_ids", []))
                    doc_count = len(indexes.get("document_ids", []))
                    msg_count = stats.get("total_messages", 0)
                    
                    if conv_count > 0 or doc_count > 0 or msg_count > 0:
                        users_with_data += 1
                    
                    total_conversations += conv_count
                    total_documents += doc_count
                    total_messages += msg_count
            
            print(f"✅ VERIFICATION RESULTS:")
            print(f"   Total Users:           {len(all_users)}")
            print(f"   Migrated Users:        {migrated_users}")
            print(f"   Users with Data:       {users_with_data}")
            print(f"   Migration Rate:        {(migrated_users / len(all_users) * 100):.1f}%")
            print(f"   Total Conversations:   {total_conversations}")
            print(f"   Total Documents:       {total_documents}")
            print(f"   Total Messages:        {total_messages}")
            
        except Exception as e:
            print(f"❌ Verification failed: {e}")

async def main():
    """Main function to run the migration"""
    print("🚀 Firebase User Migration Script")
    print("=" * 50)
    
    # Initialize the migration script
    migration = MigrationScript()
    migration.initialize_firebase()
    
    if not migration.initialized:
        print("❌ Could not initialize Firebase. Exiting.")
        return
    
    try:
        # Ask user for confirmation
        print(f"\n⚠️  This script will migrate ALL users to the indexed structure.")
        print(f"   It's safe to run multiple times (skips already migrated users).")
        
        response = input(f"\n❓ Continue with migration? (y/N): ").lower().strip()
        
        if response not in ['y', 'yes']:
            print("❌ Migration cancelled by user.")
            return
        
        # Run the migration
        await migration.migrate_all_users()
        
        # Verify results
        await migration.verify_migration()
        
        print(f"\n🎉 All done! Your FastAPI endpoints will now use indexed lookups for blazing fast performance!")
        print(f"   You can now restart your FastAPI server and enjoy the speed boost! 🚀")
        
    except KeyboardInterrupt:
        print(f"\n❌ Migration interrupted by user.")
    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        raise

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())