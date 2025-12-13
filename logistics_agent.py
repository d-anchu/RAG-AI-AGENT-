import os
import warnings
import time
import sys
# --- WORKING IMPORTS ONLY ---
# We removed 'langchain.chains' to stop the crash.
from langchain_community.llms import Ollama
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from qdrant_client import QdrantClient
# --- Language Tools ---
from langdetect import detect, DetectorFactory
from deep_translator import GoogleTranslator

DetectorFactory.seed = 0
warnings.filterwarnings("ignore")
# --- CONFIGURATION ---
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "logistics_db"
OLLAMA_MODEL = "llama3.2"
# Same models as ingest.py
DENSE_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
SPARSE_MODEL_NAME = "prithivida/Splade_PP_en_v1"


class LogisticsAgent:
    def __init__(self):
        print(f"\n🌍 LOGISTICS NEXUS (Manual Mode)")
        print("---------------------------------------")
        print(f"--> Initializing AI Core ({OLLAMA_MODEL})...")

        # 1. Initialize Embeddings
        self.dense_embeddings = FastEmbedEmbeddings(model_name=DENSE_MODEL_NAME)
        self.sparse_embeddings = FastEmbedSparse(model_name=SPARSE_MODEL_NAME)
        # 2. Connect to Qdrant
        print(f"   ...Connecting to Qdrant ({QDRANT_URL})...")
        try:
            self.client = QdrantClient(url=QDRANT_URL)
            if not self.client.collection_exists(COLLECTION_NAME):
                print(f"❌ Error: Collection '{COLLECTION_NAME}' not found.")
                print("   Run 'ingest.py' first!")
                sys.exit(1)

            self.db = QdrantVectorStore.from_existing_collection(
                embedding=self.dense_embeddings,
                sparse_embedding=self.sparse_embeddings,
                collection_name=COLLECTION_NAME,
                url=QDRANT_URL,
                retrieval_mode="hybrid"
            )
        except Exception as e:
            print(f"❌ Connection Failed: {e}")
            sys.exit(1)
        self.llm = Ollama(model=OLLAMA_MODEL)
        print("--> System Online.")

    def process_query(self, user_input):
        start_time = time.time()
        print(f"   (Analyzing input...)")
        # 1. Detect Language
        try:
            user_lang = detect(user_input)
        except:
            user_lang = "en"
        # 2. Translate to English if needed
        query_english = user_input
        if user_lang != 'en':
            try:
                query_english = GoogleTranslator(source='auto', target='en').translate(user_input)
            except:
                pass
        try:
            # --- MANUAL RETRIEVAL (Bypasses the broken Chain) ---
            # Search for top 5 documents
            docs = self.db.similarity_search(query_english, k=5)

            # Combine context into a string
            context_text = "\n\n".join([d.page_content for d in docs])

            # Extract sources for display
            sources_list = []
            for doc in docs:
                src = doc.metadata.get('source', 'Unknown')
                sources_list.append({"metadata": {"source": src}})
            # --- MANUAL GENERATION ---
            # We construct the prompt string manually
            prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
You are a Logistics Assistant. Use the Context below to answer the Question.
If the answer is not in the context, say "Data not found".
Context:
{context_text}
<|eot_id|><|start_header_id|>user<|end_header_id|>
Question: {query_english}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""
            # Call Ollama directly
            answer_english = self.llm.invoke(prompt)
        except Exception as e:
            return {
                "answer": f"System Error: {e}",
                "sources": [],
                "processing_time": 0
            }
        # 3. Translate Answer Back
        final_answer = answer_english
        if user_lang != 'en':
            try:
                final_answer = GoogleTranslator(source='en', target=user_lang).translate(answer_english)
            except:
                pass
        end_time = time.time()
        return {
            "answer": final_answer,
            "sources": sources_list,
            "processing_time": round(end_time - start_time, 2)
        }


if __name__ == "__main__":
    bot = LogisticsAgent()
    while True:
        q = input("\nUser: ")
        if q.lower() in ['exit', 'quit']: break
        response = bot.process_query(q)
        print(f"🤖 Agent: {response['answer']}")
        if response['sources']:
            # Unique sources only
            srcs = list(set([os.path.basename(s['metadata']['source']) for s in response['sources']]))
            print(f"📚 Sources: {', '.join(srcs)}")
