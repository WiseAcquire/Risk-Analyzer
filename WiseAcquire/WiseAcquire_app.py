# -*- coding: utf-8 -*-
"""app.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1p7Ef13LULpVGcvXTjI7MQHdrFr51zMNb
"""

# === STREAMLIT DEPLOYMENT VERSION ===

# STEP 1: Import Required Libraries
import os
import io
import glob
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_unstructured import UnstructuredLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.schema import Document as LCDocument
from PyPDF2 import PdfReader
from docx import Document
import warnings
import shutil
import streamlit as st
import streamlit.components.v1 as components


warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=pd.errors.ParserWarning)

# STEP 2: Load Environment Variables
load_dotenv()
IFI_API_KEY = os.getenv("IFI_API_KEY")  # <-- ADD YOUR API KEY to .streamlit/secrets.toml or env vars

# STEP 3: Ensure necessary folders exist before file operations
for folder in ['historical_documents', 'risks_document', 'target_document', 'outputs']:
    Path(folder).mkdir(parents=True, exist_ok=True)

# STEP 4: Define the RAG Risk Analysis Class
class RAGProcurementRisksAnalysis:
    def __init__(self, api_key, query, historical_documents_folder_path, risks_document_folder_path, target_document_folder_path, risk_analysis_output_path):
        self.api_key = api_key
        self.query = query
        self.historical_documents = self.load_documents(historical_documents_folder_path)
        self.risks_document = self.load_documents(risks_document_folder_path)
        self.target_document = self.load_documents(target_document_folder_path)
        self.risk_analysis_output_path = risk_analysis_output_path

    def load_documents(self, folder_path):
        all_documents = []
        supported_exts = ["csv", "pdf", "docx"]
        for ext in supported_exts:
            files = glob.glob(f"{folder_path}/*.{ext}")
            for file_path in files:
                try:
                    if file_path.endswith(".csv"):
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                        except UnicodeDecodeError:
                            with open(file_path, "r", encoding="latin1") as f:
                                content = f.read()
                        doc = LCDocument(page_content=content)
                        all_documents.append(doc)

                    else:
                        loader = UnstructuredLoader(file_path=file_path)
                        documents = loader.load()
                        all_documents.extend(documents)
                except Exception as e:
                    print(f"⚠️ Could not load {file_path}: {e}")
        print(f"📄 Loaded {len(all_documents)} docs from {folder_path}")
        return all_documents

    def create_embeddings(self):
        embeddings = OpenAIEmbeddings(openai_api_key=self.api_key)
        vector_store = FAISS.from_documents(self.historical_documents, embeddings)
        return vector_store, embeddings

    def semantic_search(self):
        vector_store, embeddings = self.create_embeddings()
        query_embedding = embeddings.embed_query(self.query)
        risks_document_embedding = embeddings.embed_query(self.risks_document[0].page_content)
        target_document_embedding = embeddings.embed_query(self.target_document[0].page_content)
    
        retrieved_by_query = vector_store.similarity_search_by_vector(query_embedding, k=3)
        retrieved_by_risks = vector_store.similarity_search_by_vector(risks_document_embedding, k=3)
        retrieved_by_target = vector_store.similarity_search_by_vector(target_document_embedding, k=3)
    
        retrieved_documents = list({doc.page_content: doc for doc in retrieved_by_query + retrieved_by_target + retrieved_by_risks}.values())

        if not retrieved_documents:
            print("⚠️ No documents retrieved during semantic search!")
    
        print(f"🔍 Retrieved {len(retrieved_documents)} relevant docs for semantic search.")
    
        return "\n\n".join([f"Document {i + 1}: {doc.page_content}" for i, doc in enumerate(retrieved_documents)])

    def save_risk_analysis_to_file(self, risk_analysis):
        file_path = f"{self.risk_analysis_output_path}/risk_analysis.txt"
        os.makedirs(self.risk_analysis_output_path, exist_ok=True)
        with open(file_path, "w") as file:
            file.write(risk_analysis)
    
    def generate_risks_analysis_rag(self):
        llm = ChatOpenAI(model="gpt-4o", temperature=0.5, openai_api_key=self.api_key)
    
        retrieved_docs_str = self.semantic_search()
        risks_content = self.risks_document[0].page_content
        target_content = self.target_document[0].page_content
    
        # Add fallback for empty inputs
        if not retrieved_docs_str.strip():
            retrieved_docs_str = "No relevant documents were retrieved. Please proceed with only risks and target documents."
    
        if not risks_content.strip():
            st.error("❌ The risks document is empty. Please upload a valid file.")
            return "Error: Risks document is empty."
    
        if not target_content.strip():
            st.error("❌ The target document is empty. Please upload a valid file.")
            return "Error: Target document is empty."
    
        # Debug logs
        print("----- Prompt Preview -----")
        print("Query:", self.query)
        print("--- Retrieved Docs ---")
        print(retrieved_docs_str[:500])
        print("--- Risks Document ---")
        print(risks_content[:500])
        print("--- Target Document ---")
        print(target_content[:500])

    
        prompt_template = PromptTemplate(
            input_variables=["retrieved_docs_str", "risks_document_content", "target_document_content"],
            template='''You are a procurement risk assessment AI. Evaluate the risks associated with the target document
    based on the retrieved knowledge and the risks detailed in the risks document.
    
    ### Target Document:
    {target_document_content}
    
    ### Risks Document:
    {risks_document_content}
    
    ### Retrieved Risk-Related Documents:
    {retrieved_docs_str}
    
    ### Task:
    Analyze the target document and classify risks into the categories detailed in the risks document.
    
    Output the risk labels and a short explanation for each.
    
    Risk Assessment:
    
    Based on the risks document summarize a mitigation plan.
    
    Mitigation Plan:'''
        )
    
        chain = LLMChain(llm=llm, prompt=prompt_template)
        risk_analysis = chain.run({
            "retrieved_docs_str": retrieved_docs_str,
            "risks_document_content": risks_content,
            "target_document_content": target_content
        })
    
        self.save_risk_analysis_to_file(risk_analysis)
        return risk_analysis


# STEP 5: Preview Function
def preview_file(file, file_type, name="Uploaded file"):
    st.subheader(f"Preview: {name}")
    if file_type == "csv":
        df = pd.read_csv(file)
        st.dataframe(df.head())
    elif file_type == "pdf":
        reader = PdfReader(file)
        text = "\n".join([page.extract_text() for page in reader.pages[:2] if page.extract_text()])
        st.markdown("#### 📑 Extracted Preview with Highlights")
        highlighted_text = text[:2000].replace("risk", "**:red[risk]**").replace("delay", "**:orange[delay]**")
        st.markdown(highlighted_text, unsafe_allow_html=True)
    elif file_type == "docx":
        doc = Document(file)
        text = "\n".join([p.text for p in doc.paragraphs])
        st.text_area("DOCX Preview", text[:2000], height=200)

# STEP 6: Streamlit UI Setup
st.set_page_config(page_title="Procurement Risk Analyzer", layout="centered")

st.title("📄 Procurement Risk Analyzer")

st.sidebar.title("ℹ️ About")
st.sidebar.info('''
This tool uses LLM-based Retrieval-Augmented Generation (RAG) to assess risks in procurement documents.

- Built with LangChain + Streamlit
- Supports CSV, PDF, and DOCX
- Preview documents before analysis
- Securely runs in your environment
''')

    st.markdown("### 📂 Upload Your Documents")
    st.markdown("Drag & drop your files below. Supported: 📄 CSV, 📑 PDF, 📝 DOCX")
    query = st.text_input("What do you want to know?", "What are the risks associated with this procurement document?")
 
    col1, col2, col3 = st.columns(3)
    with col1:
        EXAMPLES_PATH = Path(__file__).resolve().parent.parent / "example_files"
        with open(EXAMPLES_PATH / "dataset1.csv", "rb") as f:
            st.markdown("📄 History Document", f, file_name="dataset1.csv", help="Historical doc example"))
    with col2:
        with open(EXAMPLES_PATH / "risks.csv", "rb") as f:
            st.markdown("📑 Risk Register", f, file_name="risks.csv", help="Risk types to reference")
    with col3:
        with open(EXAMPLES_PATH / "dataset_no_risks.csv", "rb") as f:
            st.markdown("📝 Target Procurement File", f, file_name="dataset_no_risks.csv", help="Target doc example")
    doc_labels = {
        "History Document": [],
        "Risk Register": None,
        "Target Procurement File": None,
    }
    
    uploaded_docs = {}
    
    for label in doc_labels:
        st.markdown(f"**{label}:**")
        uploaded_file = st.file_uploader(
            f"Upload your {label}", 
            type=["csv", "pdf", "docx"], 
            key=label,
            help={
                "History Document": "📚 Upload past procurement records. These help the model understand project patterns.",
                "Risk Register": "⚠️ Upload a file listing types of risks and descriptions (e.g., Risk Doc.csv).",
                "Target Procurement File": "🎯 Upload the project document you want to analyze (e.g., Target.csv)."
            }.get(label, "")
        )
        
        if uploaded_file:
            st.success(f"✅ Uploaded: {uploaded_file.name}")
            file_ext = uploaded_file.name.split(".")[-1]
            bytes_data = uploaded_file.getvalue()
            
            st.text(f"🧪 Uploaded {label}: {uploaded_file.name}, size: {len(bytes_data)} bytes")
            preview_file(io.BytesIO(bytes_data), file_ext, name=uploaded_file.name)
    
            # Save uploaded files appropriately
            if label == "History Document":
                doc_labels["History Document"].append((uploaded_file.name, bytes_data))
            else:
                doc_labels[label] = (uploaded_file.name, bytes_data)
            
            uploaded_docs[label] = uploaded_file

if st.button("Run Analysis"):
    if not IFI_API_KEY:
        st.error("Missing API key!")
    elif not historical_files or not risks_file or not target_file:
        st.warning("Please upload all required files.")
    else:
        with st.spinner("Processing files and analyzing..."):
            base_dir = Path(".")

            # Save historical files
            for fname, fbytes in historical_file_bytes:
                with open(base_dir / "historical_documents" / fname, "wb") as out:
                    out.write(fbytes)

            # Save risks file
            risks_path = base_dir / "risks_document" / risks_file.name
            with open(risks_path, "wb") as out:
                out.write(risks_bytes)

            # Save target file
            target_path = base_dir / "target_document" / target_file.name
            with open(target_path, "wb") as out:
                out.write(target_bytes)

            # Run RAG analysis
            rag = RAGProcurementRisksAnalysis(
                api_key=IFI_API_KEY,
                query=query,
                historical_documents_folder_path=base_dir / "historical_documents",
                risks_document_folder_path=base_dir / "risks_document",
                target_document_folder_path=base_dir / "target_document",
                risk_analysis_output_path=base_dir / "outputs"
            )

            st.text(f"📄 Loaded {len(rag.risks_document)} risks doc(s)")
            if rag.risks_document:
                st.text(f"🔎 Risks doc preview:\n{rag.risks_document[0].page_content[:300]}")

            if not rag.historical_documents:
                st.error("❌ Could not load any content from historical documents.")
            elif not rag.risks_document:
                st.error("❌ Could not load any content from the risks document.")
            elif not rag.target_document:
                st.error("❌ Could not load any content from the target document.")
            else:
                result = rag.generate_risks_analysis_rag()
                st.success("✅ Analysis complete!")
                st.markdown("### 📊 Risk Summary Panel")

                # Simulated values – replace with parsed values later
                col1, col2, col3 = st.columns(3)
                col1.metric("🟥 High Risks", "2")
                col2.metric("🟧 Medium Risks", "3")
                col3.metric("🟩 Low Risks", "4")
                
                st.markdown("**📈 Budget Variance:** $700,000 Overrun")
                st.markdown("**🕒 Schedule Variance:** +15 days late")
                
                # Visual risk score (simulate with bar)
                st.progress(0.68)
                st.markdown("**Risk Score:** 68/100 — Moderate")
                

                st.markdown("### 📤 Export & Share")
                with st.spinner("Generating full report..."):
                    st.download_button("📄 Download as PDF", result, file_name="risk_analysis.pdf")
                    st.download_button("📊 Export to Excel", result, file_name="risk_analysis.xlsx")
                    st.download_button("💾 Export as JSON", result, file_name="risk_analysis.json")

                if "Mitigation Plan:" in result:
                    risk_section, mitigation_section = result.split("Mitigation Plan:", 1)
                else:
                    risk_section = result
                    mitigation_section = ""

                with st.expander("📋 Risk Explorer Panel", expanded=True):
                    st.markdown("Filter and review each risk found:")
                
                    # Simulate parsed risks
                    parsed_risks = [
                        {"title": "Phase 1 Delay", "type": "📅 Schedule", "severity": "High", "confidence": 87, "key_data": "15 days late", "mitigation": "Reschedule milestone with buffer"},
                        {"title": "Supplier Budget Overrun", "type": "💰 Cost", "severity": "Medium", "confidence": 75, "key_data": "$200K over", "mitigation": "Re-negotiate supplier terms"},
                    ]
                
                    for i, risk in enumerate(parsed_risks):
                        with st.expander(f"{risk['type']} **{risk['title']}** — {risk['severity']} Risk ({risk['confidence']}%)"):
                            st.markdown(f"**Key Insight:** {risk['key_data']}")
                            st.markdown(f"**Mitigation Plan:** {risk['mitigation']}")
                st.markdown("### ⏱️ Timeline View")
                st.markdown("Visualize risk timing across project phases")
                
                import plotly.express as px
                import pandas as pd
                
                timeline_data = pd.DataFrame([
                    dict(Task="Planning", Start='2024-01-01', Finish='2024-01-15', Risk="None"),
                    dict(Task="Phase 1", Start='2024-01-16', Finish='2024-02-15', Risk="Delay"),
                    dict(Task="Phase 2", Start='2024-02-16', Finish='2024-03-15', Risk="Cost Overrun"),
                ])
                
                fig = px.timeline(timeline_data, x_start="Start", x_end="Finish", y="Task", color="Risk")
                st.plotly_chart(fig, use_container_width=True)



                if mitigation_section.strip():
                    with st.expander("🛡️ Mitigation Panel", expanded=True):
                        mitigation_items = mitigation_section.strip().split("\n")
                        for m in mitigation_items:
                            st.checkbox(f"🛠 {m.strip()}")
