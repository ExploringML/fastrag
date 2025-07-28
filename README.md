# FastHTML RAG (Retrieval-Augmented Generation)

A **FastHTML-powered RAG system** that provides intelligent, context-aware answers about FastHTML framework documentation using **Claude AI** and **real-time streaming responses**.

![FastHTML RAG Demo](https://img.shields.io/badge/FastHTML-RAG-blue?style=for-the-badge&logo=python&logoColor=white)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🚀 Features

### ✨ **Core Functionality**
- **🔍 Semantic Search**: Vector-based similarity search using sentence transformers
- **🤖 AI-Powered Answers**: Real-time streaming responses from Claude AI
- **📚 RAG Integration**: Context-aware answers using FastHTML documentation
- **⚡ Side-by-Side Comparison**: Compare RAG vs non-RAG responses in real-time
- **🧠 LLM Context Transparency**: View the exact prompts and context sent to Claude

### 🎯 **User Experience**
- **📱 Modern UI**: Clean, responsive design with Tailwind CSS
- **⏱️ Real-time Streaming**: Watch answers appear as they're generated
- **🔄 HTMX-First**: Server-side rendering with minimal JavaScript
- **📖 Progressive Markdown**: Real-time markdown rendering with syntax highlighting
- **🎨 FastHTML Best Practices**: Built following FastHTML conventions

### 🛠️ **Technical Features**
- **🗄️ LanceDB Vector Storage**: High-performance vector database
- **🔧 Modular Architecture**: Clean separation of concerns
- **📊 Batch Processing**: Automated documentation ingestion
- **🌐 Web Scraping**: Automatic FastHTML documentation collection
- **🔐 Secure**: Environment-based API key management

## 📋 Prerequisites

- **Python 3.12+**
- **Anthropic API Key** (Claude AI)
- **uv** package manager (recommended) or pip

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/fasthtml-rag.git
cd fasthtml-rag
```

### 2. Install Dependencies
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

### 3. Set Up Environment
Create a `.env` file in the project root:
```env
ANTHROPIC_API_KEY=your_claude_api_key_here
```

### 4. Initialize the Database
```bash
# Run the batch processing to populate the vector database
uv run utils/batch.py
```

### 5. Start the Application
```bash
uv run chunk_data.py
```

Visit `http://localhost:5001` to access the RAG system!

## 🏗️ Project Structure

```
fasthtml-rag/
├── chunk_data.py           # Main FastHTML application
├── pyproject.toml          # Project dependencies and metadata
├── .env                    # Environment variables (create this)
├── docs/                   # FastHTML reference documentation
│   ├── fasthtml_ref.md     # Concise FastHTML reference
│   ├── best_practices.md   # FastHTML best practices
│   └── by_example.md       # FastHTML examples
├── utils/                  # Utility modules
│   ├── __init__.py
│   ├── batch.py           # Batch processing for documentation
│   ├── claude_service.py  # Claude AI integration
│   ├── database.py        # LanceDB vector database
│   └── scraper.py         # Web scraping utilities
├── lancedb/               # Vector database storage
│   ├── fasthtml_chunks.lance/  # Chunked documentation vectors
│   └── fasthtml_docs.lance/    # Full document vectors
└── README.md              # This file
```

## 🔧 Architecture

### **FastHTML Components**
- **Main App**: `chunk_data.py` - FastHTML application with HTMX routing
- **UI Components**: Server-side rendered components with Tailwind CSS
- **Streaming**: Server-Sent Events (SSE) for real-time AI responses

### **RAG Pipeline**
1. **Document Ingestion**: Web scraping → Text extraction → Chunking
2. **Vector Storage**: Sentence transformers → LanceDB vector storage
3. **Query Processing**: User query → Semantic search → Context retrieval
4. **AI Generation**: Context + Query → Claude AI → Streaming response

### **Data Flow**
```
User Query → Semantic Search → Context Retrieval → Claude AI → Streaming Response
     ↓              ↓                ↓              ↓           ↓
  FastHTML     LanceDB         Context Builder   Claude API   SSE Stream
```

## 🎯 Usage

### **Single Answer Mode**
1. Enter your FastHTML question
2. Click "🤖 Search & Generate AI Answer"
3. Watch the AI response stream in real-time
4. View source documentation and LLM context used

### **Comparison Mode**
1. Enable "Compare with/without RAG"
2. Ask your question
3. See side-by-side streaming comparison:
   - **Left**: RAG-enhanced answer (with documentation context)
   - **Right**: Standard Claude answer (without context)
4. Compare the LLM contexts used for each response

### **Key Features**
- **📚 Source Documentation**: See which docs were used for context
- **🧠 LLM Context**: View the exact system prompts and user messages
- **⚡ Real-time Streaming**: Responses appear as they're generated
- **🔍 Semantic Search**: Find relevant docs using vector similarity

## 🛠️ Development

### **Adding New Documentation**
1. Add URLs to `utils/batch.py:fasthtml_doc_urls`
2. Run batch processing: `uv run utils/batch.py`
3. Restart the application

### **Customizing the UI**
- Modify FastHTML components in `chunk_data.py`
- Update Tailwind classes for styling
- Add new routes and handlers as needed

### **Extending Functionality**
- **New AI Models**: Update `utils/claude_service.py`
- **Different Embeddings**: Modify `utils/database.py`
- **Additional Features**: Add new components and routes

## 📦 Dependencies

### **Core Libraries**
- **FastHTML**: Web framework and UI components
- **Anthropic**: Claude AI API client
- **LanceDB**: Vector database
- **Sentence Transformers**: Text embeddings
- **BeautifulSoup4**: Web scraping and parsing

### **UI & Styling**
- **Tailwind CSS**: Utility-first CSS framework
- **HTMX**: Server-side rendering with dynamic updates
- **Zero-MD**: Real-time markdown rendering
- **HighlightJS**: Syntax highlighting

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes following FastHTML best practices
4. Test your changes thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **FastHTML Team**: For the amazing web framework
- **Anthropic**: For Claude AI and excellent API
- **LanceDB**: For the high-performance vector database
- **Community**: For FastHTML documentation and examples

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/fasthtml-rag/issues)
- **FastHTML Docs**: [fastht.ml/docs](https://www.fastht.ml/docs/)
- **Claude AI**: [docs.anthropic.com](https://docs.anthropic.com/)

---

**Built with ❤️ using FastHTML and Claude AI**