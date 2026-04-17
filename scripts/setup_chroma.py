# Run once to initialize ChromaDB collections before first use
# Usage: python scripts/setup_chroma.py

import chromadb


def setup():
    client = chromadb.HttpClient(host="localhost", port=8001)

    client.get_or_create_collection("fix_memory")
    client.get_or_create_collection("codebase_embeddings")

    print("ChromaDB collections initialized.")


if __name__ == "__main__":
    setup()
