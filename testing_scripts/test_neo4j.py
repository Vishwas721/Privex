import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
user = os.getenv("NEO4J_USERNAME", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "password123")

print(f"🔍 Testing connection to: {uri} with user: {user}")

try:
    # Enable verbose logging for the driver
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print("✅ SUCCESS: Raw driver connected perfectly!")
    driver.close()
except Exception as e:
    print("\n❌ FAILURE: Raw driver could not connect.")
    print(f"Exception Type: {type(e).__name__}")
    print(f"Exact Error: {e}")
