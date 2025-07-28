from fasthtml.common import *
from fasthtml.components import Zero_md
from utils.database import FastHTMLDatabase
from utils.claude_service import ClaudeService
from utils.batch import fasthtml_doc_urls, process_single_url
import time
import asyncio
import os
import json
from starlette.responses import StreamingResponse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

hdrs = (
    Script(src="https://cdn.tailwindcss.com"),
    Script(type="module", src="https://cdn.jsdelivr.net/npm/zero-md@3?register"),
    HighlightJS(langs=['python', 'javascript', 'html', 'css', 'bash', 'json']),
    Script(src="https://unpkg.com/monaco-editor@0.44.0/min/vs/loader.js"),
    Style("""
        /* Smooth transitions for streaming content to reduce flashing */
        .streaming-content {
            transition: all 0.2s ease-in-out;
            opacity: 1;
        }
        
        .streaming-content zero-md {
            transition: opacity 0.15s ease-in-out;
        }
        
        /* Prevent layout shifts during streaming */
        .streaming-content.final {
            transition: none;
        }
        
        /* HTMX loading indicators */
        .htmx-indicator {
            opacity: 0;
            transition: opacity 200ms ease-in;
        }
        
        .htmx-request .htmx-indicator {
            opacity: 1;
        }
        
        /* Smooth form submission feedback */
        .htmx-request {
            cursor: wait;
        }
    """),
    Script("""
        // Minimal JS only for Monaco editor - everything else uses HTMX
        require.config({ paths: { 'vs': 'https://unpkg.com/monaco-editor@0.44.0/min/vs' }});
        
        let xmlEditor;
        let monacoReady = false;

        function initMonacoOnce() {
            if (monacoReady) return;
            
            require(['vs/editor/editor.main'], function () {
                xmlEditor = monaco.editor.create(document.getElementById('xml-viewer'), {
                    value: '',
                    language: 'xml',
                    theme: 'vs-light',
                    readOnly: true,
                    wordWrap: 'on',
                    minimap: { enabled: false }
                });
                monacoReady = true;
            });
        }

        function updateXmlContent(content) {
            if (monacoReady && xmlEditor) {
                xmlEditor.setValue(content);
            } else {
                setTimeout(() => updateXmlContent(content), 100);
            }
        }
        """)
)

app = FastHTML(hdrs=hdrs, pico=False, exts='ws')

# --- FIX: Create a single, global instance of the database ---
# This ensures the DB connection and ML model are loaded only ONCE.
db = FastHTMLDatabase()

# Initialize Claude service
claude = ClaudeService()

# Global variable for progress tracking
batch_running = False

# Global variables for search results (simple session storage)
last_search_results = []
last_query = ""

# Markdown rendering function using zero-md
def render_markdown(content, css=''):
    """Render markdown content using zero-md component"""
    if css:
        css_template = Template(Style(css), data_append=True)
        return Zero_md(css_template, Script(content, type="text/markdown"))
    else:
        return Zero_md(Script(content, type="text/markdown"))

def ProgressDisplay(progress=0, text="Ready to process URLs", current=0, total=0, **kwargs):
    progress_bar_visual = Div(
        Div(
            f'{progress}%',
            cls="text-white text-center leading-6 transition-all duration-300",
            style=f'width: {progress}%; background-color: #3b82f6;'
        ),
        cls="w-full bg-gray-200 rounded h-6 overflow-hidden"
    )
    status_text = f"{current}/{total} - {text}" if total > 0 else text
    return Div(
        H3("Progress", cls="text-lg font-semibold mb-2"),
        progress_bar_visual,
        P(status_text, cls="text-sm text-gray-600 mt-2"),
        id='progress-display',
        cls="mb-6"
    )

def StartButton(disabled=False, **kwargs):
    return Button(
        'Start Batch Process',
        ws_send=True,
        id='start-button',
        disabled=disabled,
        cls=f"px-6 py-3 rounded font-semibold {'bg-gray-400 cursor-not-allowed' if disabled else 'bg-blue-500 hover:bg-blue-600'} text-white",
        **kwargs
    )

def LogContainer(**kwargs):
    return Div(
        Div(id="log-content", cls="mt-6 bg-gray-50 p-4 rounded max-h-96 overflow-y-auto"),
        Button("Clear Log", 
               hx_post="/clear-log",
               hx_target="#log-content",
               hx_swap="innerHTML",
               cls="mt-2 bg-gray-500 text-white px-4 py-2 rounded"),
        id="log-container",
        **kwargs
    )

def DatabaseStats(doc_count, chunk_count, **kwargs):
    """A dedicated component for the database stats to allow for easy OOB swaps."""
    return Div(
        Div(f"Documents: {doc_count}", cls="bg-blue-100 p-4 rounded"),
        Div(f"Chunks: {chunk_count}", cls="bg-green-100 p-4 rounded"),
        cls="grid grid-cols-2 gap-4 mb-6",
        id="db-stats",
        **kwargs
    )

def DocumentViewerModern(**kwargs):
    """Modern document viewer component with card layout"""
    docs = db.get_all_documents()
    
    if not docs:
        return Div(
            Div(
                Div(
                    Div("📂", cls="text-4xl mb-3"),
                    H3("No Documents Available", cls="text-xl font-bold text-gray-800 mb-2"),
                    P("Run the batch process first to index FastHTML documentation.", cls="text-gray-600 mb-4"),
                    cls="text-center"
                ),
                cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8"
            ),
            cls="mb-8"
        )
    
    return Div(
        Div(
            Div(
                H2("View Processed Documents", cls="text-2xl font-bold text-gray-900 mb-2"),
                P(f"Browse through {len(docs)} processed documents and their content chunks", cls="text-gray-600 mb-4"),
                Button(
                    Span("👁️ Hide Viewer", cls="mr-2"),
                    id="toggle-viewer-btn",
                    hx_post="/toggle-viewer",
                    hx_target="#viewer-content",
                    hx_swap="outerHTML",
                    cls="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors duration-200 text-sm font-medium"
                ),
                cls="mb-6"
            ),
            
            Div(
                Div(
                    Select(
                        Option("📋 Select a document to view...", value=""),
                        *[Option(f"📄 {doc['title'] or doc['url'].split('/')[-1]}", value=doc['id']) 
                          for doc in docs],
                        id="doc-selector",
                        name="doc_id",
                        hx_post="/load-doc",
                        hx_target="#content-container",
                        hx_trigger="change",
                        hx_swap="innerHTML",
                        cls="w-full p-3 border-2 border-gray-200 rounded-xl focus:border-blue-500 focus:outline-none transition-colors duration-200 text-gray-700 bg-white"
                    ),
                    cls="mb-6"
                ),
                Div(id="content-container", cls="hidden"),
                id="viewer-content"
            ),
            cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6"
        ),
        cls="mb-8",
        **kwargs
    )

def ProgressDisplayModern(**kwargs):
    """Modern progress display component"""
    return Div(
        Div(
            H3("Processing Progress", cls="text-lg font-bold text-gray-800 mb-3"),
            Div(
                Div(
                    "0%",
                    cls="text-white text-center leading-8 transition-all duration-300 bg-blue-600 rounded-lg h-8",
                    style="width: 0%;"
                ),
                cls="w-full bg-gray-200 rounded-lg h-8 overflow-hidden mb-3"
            ),
            P("Ready to process URLs", cls="text-sm text-gray-600"),
            cls="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-4 border border-blue-200"
        ),
        id='progress-display',
        **kwargs
    )

def StartButtonModern(**kwargs):
    """Modern start button component"""
    return Button(
        Div(
            Span("🚀", cls="mr-2"),
            Span("Start Processing", cls="font-semibold"),
            cls="flex items-center justify-center"
        ),
        ws_send=True,
        id='start-button',
        cls="w-full px-8 py-4 bg-gradient-to-r from-green-600 to-green-700 text-white rounded-xl hover:from-green-700 hover:to-green-800 transition-all duration-200 shadow-lg transform hover:scale-[1.02] focus:outline-none focus:ring-4 focus:ring-green-300 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none",
        **kwargs
    )

def LogContainerModern(**kwargs):
    return Div(
        Div(
            H3("Processing Log", cls="text-lg font-semibold"),
            Button(
                "Hide",
                id="toggle-log-btn",
                hx_post="/toggle-log",
                hx_target="#log-content-wrapper",
                hx_swap="outerHTML",
                cls="ml-4 px-3 py-1 bg-gray-500 text-white rounded text-sm hover:bg-gray-600"
            ),
            cls="flex items-center mb-2"
        ),
        Div(
            Div(id="log-content", cls="mt-6 bg-gray-50 p-4 rounded max-h-96 overflow-y-auto"),
            Button("Clear Log", 
                   hx_post="/clear-log", 
                   hx_target="#log-content",
                   hx_swap="innerHTML",
                   cls="mt-2 bg-gray-500 text-white px-4 py-2 rounded"),
            id="log-content-wrapper"
        ),
        id="log-container",
        **kwargs
    )

def Sidebar(current_route="/", **kwargs):
    """Modern sidebar navigation component"""
    nav_items = [
        {"href": "/", "icon": "🤖", "label": "RAG Assistant", "active": current_route == "/"},
        {"href": "/source-data", "icon": "📊", "label": "Source Data", "active": current_route == "/source-data"}
    ]
    
    return Aside(
        # Logo/Brand Section
        Div(
            Div(
                Span("🚀", cls="text-2xl"),
                H1("FastHTML RAG", cls="text-xl font-bold text-white ml-3"),
                cls="flex items-center"
            ),
            cls="p-6 border-b border-indigo-700"
        ),
        
        # Navigation Menu
        Nav(
            Ul(
                *[Li(
                    A(
                        Span(item["icon"], cls="text-xl"),
                        Span(item["label"], cls="ml-3 font-medium"),
                        href=item["href"],
                        cls=f"flex items-center px-6 py-3 text-indigo-100 hover:bg-indigo-700 hover:text-white transition-colors duration-200 {'bg-indigo-700 text-white border-r-4 border-white' if item['active'] else ''}"
                    ),
                    cls="mb-1"
                ) for item in nav_items],
                cls="space-y-1"
            ),
            cls="flex-1 px-3 py-6"
        ),
        
        # Footer
        Div(
            P("FastHTML RAG v1.0", cls="text-indigo-300 text-sm text-center"),
            cls="p-6 border-t border-indigo-700"
        ),
        
        cls="fixed left-0 top-0 h-screen w-64 bg-gradient-to-br from-indigo-800 to-indigo-900 shadow-xl flex flex-col",
        **kwargs
    )

def MainLayout(content, current_route="/", **kwargs):
    """Main layout container with sidebar"""
    return Div(
        Sidebar(current_route=current_route),
        Div(
            content,
            cls="ml-64 min-h-screen bg-gray-50"
        ),
        cls="flex",
        **kwargs
    )

@app.get('/')
def home():
    """Main RAG interface"""
    doc_count = db.get_document_count()
    chunk_count = db.get_chunk_count()
    
    content = Div(
        # Header Section
        Div(
            Div(
                H1("AI-Powered FastHTML Assistant", cls="text-3xl font-bold text-gray-900 mb-2"),
                P("Get instant, accurate answers from FastHTML documentation using advanced RAG technology", 
                  cls="text-lg text-gray-600"),
                cls="text-center"
            ),
            cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8 mb-8"
        ),
        
        # Stats Cards
        Div(
            Div(
                Div(
                    Div("📚", cls="text-3xl mb-2"),
                    Div(f"{doc_count:,}", cls="text-2xl font-bold text-blue-600 mb-1"),
                    P("Documents Indexed", cls="text-sm text-gray-600 font-medium"),
                    cls="text-center"
                ),
                cls="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-6 border border-blue-200"
            ),
            Div(
                Div(
                    Div("🧠", cls="text-3xl mb-2"),
                    Div(f"{chunk_count:,}", cls="text-2xl font-bold text-green-600 mb-1"),
                    P("Knowledge Chunks", cls="text-sm text-gray-600 font-medium"),
                    cls="text-center"
                ),
                cls="bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-6 border border-green-200"
            ),
            Div(
                Div(
                    Div("⚡", cls="text-3xl mb-2"),
                    Div("< 2s", cls="text-2xl font-bold text-purple-600 mb-1"),
                    P("Average Response", cls="text-sm text-gray-600 font-medium"),
                    cls="text-center"
                ),
                cls="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-6 border border-purple-200"
            ),
            cls="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8"
        ),
        
        # Query Interface Card
        Div(
            Div(
                Div(
                    H2("Ask Your Question", cls="text-2xl font-bold text-gray-900 mb-2"),
                    P("Type your FastHTML question below and get AI-powered answers with relevant documentation.", 
                      cls="text-gray-600 mb-6"),
                    cls="mb-6"
                ),
                
                Form(
                    Div(
                        Textarea(
                            placeholder="Example: How do I create a form with validation in FastHTML? How does routing work?",
                            name="query",
                            id="query-input",
                            cls="w-full p-4 border-2 border-gray-200 rounded-xl resize-none focus:border-blue-500 focus:outline-none transition-colors duration-200 text-gray-700",
                            rows="4"
                        ),
                        cls="mb-4"
                    ),
                    
                    # Sample Questions - using HTMX to populate the form
                    Div(
                        P("💡 Try these sample questions:", cls="text-sm font-medium text-gray-700 mb-3"),
                        Div(
                            Button(
                                "How do I implement WebSocket real-time communication in FastHTML?",
                                type="button",
                                hx_post="/set-query",
                                hx_vals='{"query": "How do I implement WebSocket real-time communication in FastHTML?"}',
                                hx_target="#query-input",
                                hx_swap="outerHTML",
                                cls="text-left px-4 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg border border-blue-200 transition-colors duration-200 text-sm"
                            ),
                            Button(
                                "What's the best way to integrate Alpine.js for client-side reactivity?",
                                type="button",
                                hx_post="/set-query",
                                hx_vals='{"query": "What\'s the best way to integrate Alpine.js for client-side reactivity?"}',
                                hx_target="#query-input",
                                hx_swap="outerHTML",
                                cls="text-left px-4 py-2 bg-green-50 hover:bg-green-100 text-green-700 rounded-lg border border-green-200 transition-colors duration-200 text-sm"
                            ),
                            Button(
                                "How can I handle file uploads and image processing with FastHTML?",
                                type="button",
                                hx_post="/set-query",
                                hx_vals='{"query": "How can I handle file uploads and image processing with FastHTML?"}',
                                hx_target="#query-input",
                                hx_swap="outerHTML",
                                cls="text-left px-4 py-2 bg-purple-50 hover:bg-purple-100 text-purple-700 rounded-lg border border-purple-200 transition-colors duration-200 text-sm"
                            ),
                            Button(
                                "How do I implement JWT authentication and session management?",
                                type="button",
                                hx_post="/set-query",
                                hx_vals='{"query": "How do I implement JWT authentication and session management?"}',
                                hx_target="#query-input",
                                hx_swap="outerHTML",
                                cls="text-left px-4 py-2 bg-amber-50 hover:bg-amber-100 text-amber-700 rounded-lg border border-amber-200 transition-colors duration-200 text-sm"
                            ),
                            Button(
                                "What's the recommended approach for database integration and ORM usage?",
                                type="button",
                                hx_post="/set-query",
                                hx_vals='{"query": "What\'s the recommended approach for database integration and ORM usage?"}',
                                hx_target="#query-input",
                                hx_swap="outerHTML",
                                cls="text-left px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-lg border border-rose-200 transition-colors duration-200 text-sm"
                            ),
                            Button(
                                "How can I build a responsive SPA with FastHTML and modern CSS frameworks?",
                                type="button",
                                hx_post="/set-query",
                                hx_vals='{"query": "How can I build a responsive SPA with FastHTML and modern CSS frameworks?"}',
                                hx_target="#query-input",
                                hx_swap="outerHTML",
                                cls="text-left px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg border border-indigo-200 transition-colors duration-200 text-sm"
                            ),
                            cls="grid grid-cols-1 md:grid-cols-2 gap-2 mb-6"
                        ),
                        cls="mb-4"
                    ),
                    Div(
                        Div(
                            Button(
                                Div(
                                    Span("🤖", cls="mr-2"),
                                    Span("Search & Generate AI Answer", cls="font-semibold"),
                                    Span("⏳ Loading...", cls="htmx-indicator ml-2"),
                                    cls="flex items-center justify-center"
                                ),
                                type="submit",
                                cls="px-8 py-4 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-xl hover:from-blue-700 hover:to-blue-800 transition-all duration-200 shadow-lg transform hover:scale-[1.02] focus:outline-none focus:ring-4 focus:ring-blue-300"
                            ),
                            cls="flex-1 mr-4"
                        ),
                        Div(
                            Label(
                                Input(
                                    type="checkbox",
                                    name="compare",
                                    cls="mr-3 w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500"
                                ),
                                Span("📊 Compare RAG vs Default", cls="text-gray-700 font-medium whitespace-nowrap"),
                                cls="flex items-center cursor-pointer"
                            ) if claude.is_available() else Div(
                                Span("🔑 API Key Required", cls="text-amber-600 font-medium text-sm"),
                                cls="flex items-center"
                            ),
                            cls="flex items-center"
                        ),
                        cls="flex items-center mb-4"
                    ),
                    hx_post="/search-and-generate",
                    hx_target="#results",
                    hx_swap="innerHTML",
                    hx_indicator=".htmx-indicator"
                ),
                cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8"
            ),
            cls="mb-8"
        ),
        
        # Results Area
        Div(id="results", cls="mb-8"),
        
        cls="p-8 max-w-6xl mx-auto"
    )
    
    return MainLayout(content, current_route="/")

@app.post('/set-query')
def set_query(query: str):
    """HTMX route to populate the query input with sample questions"""
    return Textarea(
        query,
        name="query",
        id="query-input",
        cls="w-full p-4 border-2 border-blue-500 rounded-xl resize-none focus:border-blue-500 focus:outline-none transition-colors duration-200 text-gray-700 bg-blue-50",
        rows="4",
        autofocus=True
    )

@app.get('/source-data')
def source_data():
    """Data management interface (original functionality)"""
    # Use the global `db` instance for a much faster initial load
    doc_count = db.get_document_count()
    chunk_count = db.get_chunk_count()
    
    content = Div(
        # Header Section
        Div(
            Div(
                H1("Source Data Management", cls="text-3xl font-bold text-gray-900 mb-2"),
                P("Process FastHTML documentation URLs and manage your knowledge base", 
                  cls="text-lg text-gray-600"),
                cls="text-center"
            ),
            cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8 mb-8"
        ),
        
        # Database Statistics Cards
        Div(
            Div(
                Div(
                    Div("📊", cls="text-3xl mb-3"),
                    H3("Database Statistics", cls="text-xl font-bold text-gray-800 mb-4"),
                    Div(
                        Div(
                            Span(f"{doc_count:,}", cls="text-2xl font-bold text-blue-600"),
                            P("Documents", cls="text-sm text-gray-600 font-medium"),
                            cls="text-center"
                        ),
                        Div(
                            Span(f"{chunk_count:,}", cls="text-2xl font-bold text-green-600"),
                            P("Knowledge Chunks", cls="text-sm text-gray-600 font-medium"),
                            cls="text-center"
                        ),
                        cls="grid grid-cols-2 gap-4"
                    ),
                    cls="text-center"
                ),
                cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6"
            ),
            cls="mb-8"
        ),
        
        # Document Viewer Section
        DocumentViewerModern(),
        
        # URL Processing Section
        Div(
            Div(
                Div(
                    Div(
                        H2("Process Documentation URLs", cls="text-2xl font-bold text-gray-900 mb-2"),
                        P(f"Process {len(fasthtml_doc_urls)} FastHTML documentation URLs to build the knowledge base", 
                          cls="text-gray-600 mb-4"),
                        Button(
                            Span("👁️ View URLs", cls="mr-2"),
                            id="toggle-urls-btn",
                            hx_post="/toggle-urls",
                            hx_target="#urls-content",
                            hx_swap="outerHTML",
                            cls="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors duration-200 text-sm font-medium"
                        ),
                        cls="mb-6"
                    ),
                    
                    Div(
                        Div(
                            H3(f"URLs to Process ({len(fasthtml_doc_urls)})", cls="text-lg font-semibold text-gray-800 mb-4"),
                            Div(
                                *[Div(
                                    Span(f"{i+1}.", cls="text-gray-500 font-mono text-sm mr-3"),
                                    Span(url.split('/')[-1] or url.split('/')[-2], cls="font-medium text-gray-800"),
                                    Div(url, cls="text-xs text-gray-500 mt-1"),
                                    cls="p-3 border-b border-gray-100 last:border-b-0 hover:bg-gray-50 transition-colors duration-150"
                                ) for i, url in enumerate(fasthtml_doc_urls)],
                                cls="bg-white rounded-lg border border-gray-200 max-h-60 overflow-y-auto"
                            ),
                            cls="mb-6"
                        ),
                        
                        # Progress and Controls
                        Div(
                            ProgressDisplayModern(),
                            StartButtonModern(),
                            cls="space-y-4"
                        ),
                        
                        id="urls-content"
                    ),
                    cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6"
                ),
                cls="mb-8"
            )
        ),
        
        Div(
            id="log-section",
            style="display: none;"
        ),
        
        cls="p-8 max-w-6xl mx-auto",
        hx_ext='ws', 
        ws_connect='/ws'
    )
    
    return MainLayout(content, current_route="/source-data")

@app.post('/search-only')
def search_only(query: str):
    """Search for similar chunks and return only search results"""
    if not query.strip():
        return Div(
            Div(
                Div("❓", cls="text-4xl mb-3"),
                H3("No Question Provided", cls="text-xl font-bold text-gray-800 mb-2"),
                P("Please enter a question about FastHTML to get started.", cls="text-gray-600"),
                cls="text-center"
            ),
            cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8"
        )
    
    try:
        # Perform similarity search
        results = db.search_similar(query, limit=5)
        
        if not results:
            return Div(
                Div(
                    Div("🔍", cls="text-4xl mb-3"),
                    H3("No Results Found", cls="text-xl font-bold text-gray-800 mb-2"),
                    P("No relevant documentation found for your query. Try rephrasing your question.", cls="text-gray-600"),
                    cls="text-center"
                ),
                cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8"
            )
        
        # Store results globally for streaming endpoints
        global last_search_results, last_query
        last_search_results = results
        last_query = query
        
        # Return only search results
        return Div(
            Div(
                H3("📚 Source Documentation", cls="text-2xl font-bold text-gray-900 mb-2"),
                P(f"Found {len(results)} relevant documents from FastHTML documentation", cls="text-gray-600 mb-6"),
                cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6"
            ),
            Div(
                *[SearchResultModern(result, i+1) for i, result in enumerate(results)],
                cls="space-y-4"
            )
        )
    
    except Exception as e:
        return Div(
            Div(
                Div("🚨", cls="text-4xl mb-3"),
                H3("Search Error", cls="text-xl font-bold text-red-800 mb-2"),
                P(f"Error performing search: {str(e)}", cls="text-red-600"),
                cls="text-center"
            ),
            cls="bg-red-50 border border-red-200 rounded-xl p-8"
        )

@app.post('/search-and-generate')
def search_and_generate(query: str, compare: bool = False):
    """Combined search and answer generation with proper HTMX SSE streaming"""
    if not query.strip():
        return Div(
            Div(
                Div("❓", cls="text-4xl mb-3"),
                H3("No Question Provided", cls="text-xl font-bold text-gray-800 mb-2"),
                P("Please enter a question about FastHTML to get started.", cls="text-gray-600"),
                cls="text-center"
            ),
            cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8"
        )
    
    try:
        # Perform similarity search
        results = db.search_similar(query, limit=5)
        
        if not results:
            return Div(
                Div(
                    Div("🔍", cls="text-4xl mb-3"),
                    H3("No Results Found", cls="text-xl font-bold text-gray-800 mb-2"),
                    P("No relevant documentation found for your query. Try rephrasing your question.", cls="text-gray-600"),
                    cls="text-center"
                ),
                cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8"
            )
        
        # Store results globally for streaming endpoints
        global last_search_results, last_query
        last_search_results = results
        last_query = query
        
        # Build the response layout with HTMX SSE streaming
        if not claude.is_available():
            # Show only search results if Claude is not available
            return Div(
                # API Key warning
                Div(
                    Div(
                        Div("🔑", cls="text-3xl mb-3"),
                        H3("AI Generation Unavailable", cls="text-xl font-bold text-amber-800 mb-2"),
                        P("Add ANTHROPIC_API_KEY to .env file to enable AI-powered answers. Showing search results only.", cls="text-amber-700"),
                        cls="text-center"
                    ),
                    cls="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-6 mb-6"
                ),
                
                # Search Results
                Div(
                    Div(
                        H3("📚 Search Results", cls="text-2xl font-bold text-gray-900 mb-2"),
                        P(f"Found {len(results)} relevant documents from FastHTML documentation", cls="text-gray-600 mb-6"),
                        cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6"
                    ),
                    Div(
                        *[SearchResultModern(result, i+1) for i, result in enumerate(results)],
                        cls="space-y-4"
                    )
                ),
                cls="space-y-6"
            )
        
        if compare:
            # Comparison mode - stream both RAG and no-RAG answers side-by-side
            try:
                return Div(
                # AI Comparison Section
                Div(
                    H3("🤖 AI Generated Answers", cls="text-2xl font-bold text-gray-900 mb-6 text-center"),
                    
                    # Side-by-side streaming comparison
                    Div(
                        # RAG Answer (Left)
                        Div(
                            H4("🎯 With RAG Context", cls="text-lg font-bold text-green-700 text-center mb-4"),
                            Div(
                                Div(id="rag-answer", cls="p-6 bg-white min-h-[300px]"),
                                cls="prose prose-sm max-w-none bg-gradient-to-br from-green-50 to-green-100 p-6 rounded-xl border border-green-200 min-h-[300px] overflow-y-auto"
                            ),
                            cls="w-1/2 pr-3"
                        ),
                        
                        # No-RAG Answer (Right)
                        Div(
                            H4("🧠 Default Claude", cls="text-lg font-bold text-blue-700 text-center mb-4"),
                            Div(
                                Div(id="no-rag-answer", cls="p-6 bg-white min-h-[300px]"),
                                cls="prose prose-sm max-w-none bg-gradient-to-br from-blue-50 to-blue-100 p-6 rounded-xl border border-blue-200 min-h-[300px] overflow-y-auto"
                            ),
                            cls="w-1/2 pl-3"
                        ),
                        cls="flex gap-6 mb-6"
                    ),
                        
                        # Comparison insights
                        Div(
                            P("💡 Compare the responses to see how RAG improves accuracy and provides specific, context-aware answers.", 
                              cls="text-sm text-gray-600 italic text-center"),
                            cls="bg-gray-50 rounded-lg p-4"
                        ),
                        
                        cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8 mb-6"
                    ),
                    
                    # Search Results
                    Div(
                        Div(
                            H3("📚 Source Documentation", cls="text-2xl font-bold text-gray-900 mb-2"),
                            P(f"Found {len(results)} relevant documents used for RAG context", cls="text-gray-600 mb-6"),
                            cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6"
                        ),
                        Div(
                            *[SearchResultModern(result, i+1) for i, result in enumerate(results)],
                            cls="space-y-4"
                        )
                    ),
                    
                    # LLM Context Section for Comparison
                    Div(
                        Div(
                            H3("🧠 LLM Context", cls="text-2xl font-bold text-gray-900 mb-2"),
                            P("Full context and system messages sent to Claude AI for comparison", cls="text-gray-600 mb-6"),
                            cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6"
                        ),
                        Div(
                            # Side-by-side context comparison
                            Div(
                                # RAG Context (Left)
                                Div(
                                    H4("🎯 RAG Context", cls="text-lg font-bold text-green-700 text-center mb-4"),
                                    *((lambda ctx: [
                                        Div(
                                            H5("📋 System Message", cls="text-md font-bold text-purple-700 mb-2"),
                                            Pre(ctx["system_message"], cls="whitespace-pre-wrap bg-purple-50 p-3 rounded border-l-4 border-purple-400 text-xs leading-relaxed overflow-x-auto max-h-48 overflow-y-auto"),
                                            cls="mb-4"
                                        ),
                                        Div(
                                            H5("💬 User Message", cls="text-md font-bold text-blue-700 mb-2"),
                                            Pre(ctx["user_message"], cls="whitespace-pre-wrap bg-blue-50 p-3 rounded border-l-4 border-blue-400 text-xs leading-relaxed overflow-x-auto max-h-48 overflow-y-auto"),
                                            cls="mb-4"
                                        )
                                    ])(claude.get_full_context(query, results))),
                                    cls="w-1/2 pr-3"
                                ),
                                
                                # No-RAG Context (Right)
                                Div(
                                    H4("🧠 No-RAG Context", cls="text-lg font-bold text-blue-700 text-center mb-4"),
                                    *((lambda ctx: [
                                        Div(
                                            H5("📋 System Message", cls="text-md font-bold text-purple-700 mb-2"),
                                            Pre(ctx["system_message"], cls="whitespace-pre-wrap bg-purple-50 p-3 rounded border-l-4 border-purple-400 text-xs leading-relaxed overflow-x-auto max-h-48 overflow-y-auto"),
                                            cls="mb-4"
                                        ),
                                        Div(
                                            H5("💬 User Message", cls="text-md font-bold text-blue-700 mb-2"),
                                            Pre(ctx["user_message"], cls="whitespace-pre-wrap bg-blue-50 p-3 rounded border-l-4 border-blue-400 text-xs leading-relaxed overflow-x-auto max-h-48 overflow-y-auto"),
                                            cls="mb-4"
                                        )
                                    ])(claude.get_full_context(query, None))),
                                    cls="w-1/2 pl-3"
                                ),
                                cls="flex gap-6"
                            ),
                            cls="space-y-4"
                        )
                    ),
                    
                    # Auto-start dual streaming JavaScript for comparison
                    Script("""
                    // Auto-start both streams immediately
                    function startComparisonStreaming() {
                        startSingleStream('rag-answer', '/generate-answer-streaming', 'RAG');
                        startSingleStream('no-rag-answer', '/generate-answer-no-rag-streaming', 'Default Claude');
                    }
                    
                    function startSingleStream(containerId, endpoint, answerType) {
                        const answerDiv = document.getElementById(containerId);
                        
                        // Create container for streaming answer
                        answerDiv.innerHTML = `
                            <div class="mb-6 border rounded-lg p-4">
                                <h5 class="text-lg font-bold mb-3 text-gray-700">🤖 ${answerType} (Streaming...)</h5>
                                <div class="prose prose-sm max-w-none p-4 rounded leading-relaxed">
                                    <div id="${containerId}-content" class="min-h-[2rem]"></div>
                                    <div id="${containerId}-cursor" class="inline-block w-2 h-4 bg-blue-500 animate-pulse ml-1"></div>
                                </div>
                            </div>
                        `;
                        
                        const streamingContent = document.getElementById(containerId + '-content');
                        const cursor = document.getElementById(containerId + '-cursor');
                        let fullContent = '';

                        // Create zero-md element for progressive markdown rendering
                        const zeroMdElement = document.createElement('zero-md');
                        const scriptElement = document.createElement('script');
                        scriptElement.type = 'text/markdown';
                        scriptElement.textContent = '';
                        zeroMdElement.appendChild(scriptElement);
                        streamingContent.appendChild(zeroMdElement);

                        // Create EventSource for Server-Sent Events
                        const eventSource = new EventSource(endpoint);
                        
                        eventSource.onmessage = function(event) {
                            if (event.data === '[DONE]') {
                                eventSource.close();
                                cursor.style.display = 'none';
                                
                                // Update title
                                const title = answerDiv.querySelector('h5');
                                if (title) title.textContent = `🤖 ${answerType}`;
                                return;
                            }
                            
                            try {
                                const data = JSON.parse(event.data);
                                
                                if (data.type === 'chunk') {
                                    fullContent += data.content;
                                    // Update the zero-md script content for progressive rendering
                                    scriptElement.textContent = fullContent;
                                } else if (data.type === 'complete') {
                                    // Final update with complete content
                                    scriptElement.textContent = data.content;
                                    cursor.style.display = 'none';
                                    
                                    // Update title
                                    const title = answerDiv.querySelector('h5');
                                    if (title) title.textContent = `🤖 ${answerType}`;
                                } else if (data.type === 'error') {
                                    console.error('Streaming error:', data.content);
                                    streamingContent.innerHTML = '<div class="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400">❌ ' + data.content + '</div>';
                                }
                            } catch (e) {
                                console.error('Error parsing SSE data:', e);
                            }
                        };
                        
                        eventSource.onerror = function(event) {
                            console.error('EventSource error:', event);
                            eventSource.close();
                            streamingContent.innerHTML = '<div class="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400">❌ Streaming connection failed.</div>';
                        };
                    }
                    
                    // Start comparison streaming immediately
                    startComparisonStreaming();
                    """),
                    cls="space-y-6"
                )
                
            except Exception as e:
                return Div(
                    Div(
                        Div("❌", cls="text-4xl mb-3"),
                        H3("Generation Error", cls="text-xl font-bold text-red-800 mb-2"),
                        P(f"Error generating comparison: {str(e)}", cls="text-red-600"),
                        cls="text-center"
                    ),
                    cls="bg-red-50 border border-red-200 rounded-xl p-8"
                )
        else:
            # Single RAG answer mode with auto-streaming
            return Div(
                # AI Answer Section with auto-streaming
                Div(
                    H3("🤖 AI Generated Answer", cls="text-2xl font-bold text-green-700 mb-4"),
                    Div(
                        Div(id="ai-answer", cls="mt-4"),
                        cls="prose max-w-none min-h-[200px]"
                    ),
                    P("💡 This answer is being streamed in real-time using context from the search results below.", 
                      cls="text-xs text-gray-500 italic mt-4 text-center"),
                    cls="bg-white rounded-xl shadow-sm border border-gray-200 p-8 mb-6"
                ),
                
                # Search Results
                Div(
                    Div(
                        H3("📚 Source Documentation", cls="text-2xl font-bold text-gray-900 mb-2"),
                        P(f"Found {len(results)} relevant documents used for context", cls="text-gray-600 mb-6"),
                        cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6"
                    ),
                    Div(
                        *[SearchResultModern(result, i+1) for i, result in enumerate(results)],
                        cls="space-y-4"
                    )
                ),
                
                # LLM Context Section
                Div(
                    Div(
                        H3("🧠 LLM Context", cls="text-2xl font-bold text-gray-900 mb-2"),
                        P("Full context and system message sent to Claude AI", cls="text-gray-600 mb-6"),
                        cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6"
                    ),
                    Div(
                        # Get the full context from Claude service
                        *((lambda ctx: [
                            Div(
                                H4("📋 System Message", cls="text-lg font-bold text-purple-700 mb-3"),
                                Pre(ctx["system_message"], cls="whitespace-pre-wrap bg-purple-50 p-4 rounded border-l-4 border-purple-400 text-sm leading-relaxed overflow-x-auto"),
                                cls="mb-6"
                            ),
                            Div(
                                H4("💬 User Message", cls="text-lg font-bold text-blue-700 mb-3"),
                                Pre(ctx["user_message"], cls="whitespace-pre-wrap bg-blue-50 p-4 rounded border-l-4 border-blue-400 text-sm leading-relaxed overflow-x-auto"),
                                cls="mb-6"
                            )
                        ])(claude.get_full_context(query, results))),
                        cls="space-y-4"
                    )
                ),
                
                # Auto-start streaming JavaScript
                Script("""
                // Auto-start streaming immediately when script loads
                function startStreamingAnswer() {
                    const answerDiv = document.getElementById('ai-answer');
                    
                    // Create container for streaming answer
                    answerDiv.innerHTML = `                        
                        <div class="prose prose-sm max-w-none bg-green-50 p-4 rounded border-l-4 border-green-400 leading-relaxed">
                            <div id="streaming-content" class="p-6 bg-white min-h-[2rem]"></div>
                            <div id="streaming-cursor" class="inline-block w-2 h-4 bg-green-500 animate-pulse ml-1"></div>
                        </div>
                    `;
                    
                    const streamingContent = document.getElementById('streaming-content');
                    const cursor = document.getElementById('streaming-cursor');
                    let fullContent = '';

                    // Create zero-md element for progressive markdown rendering
                    const zeroMdElement = document.createElement('zero-md');
                    const scriptElement = document.createElement('script');
                    scriptElement.type = 'text/markdown';
                    scriptElement.textContent = '';
                    zeroMdElement.appendChild(scriptElement);
                    streamingContent.appendChild(zeroMdElement);

                    // Create EventSource for Server-Sent Events
                    const eventSource = new EventSource('/generate-answer-streaming');
                    
                    eventSource.onmessage = function(event) {
                        if (event.data === '[DONE]') {
                            eventSource.close();
                            cursor.style.display = 'none';
                            
                            // Update title
                            const title = answerDiv.querySelector('h3');
                            if (title) title.textContent = '🤖 AI Generated Answer (with RAG)';
                            return;
                        }
                        
                        try {
                            const data = JSON.parse(event.data);
                            
                            if (data.type === 'chunk') {
                                fullContent += data.content;
                                // Update the zero-md script content for progressive rendering
                                scriptElement.textContent = fullContent;
                            } else if (data.type === 'complete') {
                                // Final update with complete content
                                scriptElement.textContent = data.content;
                                cursor.style.display = 'none';
                                
                                // Update title
                                const title = answerDiv.querySelector('h3');
                                if (title) title.textContent = '🤖 AI Generated Answer (with RAG)';
                            } else if (data.type === 'error') {
                                console.error('Streaming error:', data.content);
                                streamingContent.innerHTML = '<div class="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400">❌ ' + data.content + '</div>';
                            }
                        } catch (e) {
                            console.error('Error parsing SSE data:', e);
                        }
                    };
                    
                    eventSource.onerror = function(event) {
                        console.error('EventSource error:', event);
                        eventSource.close();
                        streamingContent.innerHTML = '<div class="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400">❌ Streaming connection failed.</div>';
                    };
                }
                
                // Start streaming immediately
                startStreamingAnswer();
                """),
                cls="space-y-6"
            )
                
    except Exception as e:
        return Div(
            Div(
                Div("🚨", cls="text-4xl mb-3"),
                H3("Search Error", cls="text-xl font-bold text-red-800 mb-2"),
                P(f"Error performing search: {str(e)}", cls="text-red-600"),
                cls="text-center"
            ),
            cls="bg-red-50 border border-red-200 rounded-xl p-8"
        )

def SearchResultModern(result, index):
    """Display a single search result with modern styling"""
    # Calculate similarity percentage (LanceDB returns distance, lower is better)
    distance = result.get('_distance', 1.0)
    similarity = max(0, (1 - distance) * 100)
    
    # Determine similarity color and badge style
    if similarity >= 80:
        badge_cls = "bg-green-100 text-green-800 border-green-200"
        similarity_icon = "🎯"
    elif similarity >= 60:
        badge_cls = "bg-blue-100 text-blue-800 border-blue-200"
        similarity_icon = "✅"
    else:
        badge_cls = "bg-gray-100 text-gray-800 border-gray-200"
        similarity_icon = "📄"
    
    content = result.get('content', '')
    preview_content = content[:400] + ('...' if len(content) > 400 else '')
    
    return Div(
        Div(
            # Header with result number and similarity score
            Div(
                Div(
                    Span(f"#{index}", cls="text-lg font-bold text-indigo-600 mr-3"),
                    Span(result.get('section_title', 'Untitled Section'), cls="text-lg font-semibold text-gray-900"),
                    cls="flex items-center"
                ),
                Div(
                    Span(similarity_icon, cls="mr-1"),
                    Span(f"{similarity:.1f}% match", cls="font-medium"),
                    cls=f"px-3 py-1 rounded-full text-sm border {badge_cls}"
                ),
                cls="flex justify-between items-start mb-4"
            ),
            
            # Content preview
            Div(
                P(preview_content, cls="text-gray-700 leading-relaxed"),
                cls="bg-gradient-to-r from-gray-50 to-gray-100 rounded-lg p-4 mb-4 border-l-4 border-indigo-400"
            ),
            
            # Footer with source link
            Div(
                A(
                    Div(
                        Span("🔗", cls="mr-2"),
                        Span(f"View source: {result.get('url', '').split('/')[-1]}", cls="font-medium"),
                        cls="flex items-center"
                    ),
                    href=result.get('url', '#'),
                    target="_blank",
                    cls="text-blue-600 hover:text-blue-800 hover:underline transition-colors duration-200"
                ),
                cls="pt-3 border-t border-gray-200"
            ),
            
            cls="bg-white rounded-xl shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow duration-200"
        )
    )

@app.post('/generate-answer')
def generate_answer():
    """Generate AI answer using Claude based on last search results"""
    global last_search_results, last_query
    
    if not claude.is_available():
        return Div(
            P("❌ Claude API not available. Please check your ANTHROPIC_API_KEY in .env file.", 
              cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
            cls="mb-4"
        )
    
    try:
        if not last_search_results:
            return Div(
                P("❌ No search results available. Please perform a search first.", 
                  cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
                cls="mb-4"
            )
        
        # Show loading indicator first
        loading_div = Div(
            P("🤖 Generating answer...", cls="text-blue-600 italic animate-pulse"),
            cls="text-center p-4"
        )
        
        # Generate answer using Claude
        answer = claude.generate_answer(last_query, last_search_results)
        
        if answer:
            return Div(
                Div(
                    # Convert markdown-like content to HTML
                    Pre(answer, cls="whitespace-pre-wrap bg-green-50 p-4 rounded border-l-4 border-green-400 text-sm leading-relaxed"),
                    cls="prose max-w-none"
                ),
                P("💡 This answer was generated by Claude AI based on the search results above.", 
                  cls="text-xs text-gray-500 italic mt-3 border-t pt-3"),
                cls=""
            )
        else:
            return Div(
                P("❌ Failed to generate answer. Please try again.", 
                  cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
                cls="mb-4"
            )
    
    except Exception as e:
        return Div(
            P(f"❌ Error generating answer: {str(e)}", 
              cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
            cls="mb-4"
        )

# Old streaming endpoints removed - now using proper HTMX SSE patterns

@app.post('/generate-comparison')
def generate_comparison():
    """Generate both RAG and No-RAG answers for comparison"""
    global last_search_results, last_query
    
    if not claude.is_available():
        return Div(
            P("❌ Claude API not available. Please check your ANTHROPIC_API_KEY in .env file.", 
              cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
            cls="mb-4"
        )
    
    if not last_search_results:
        return Div(
            P("❌ No search results available. Please perform a search first.", 
              cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
            cls="mb-4"
        )
    
    try:
        # Generate both answers
        rag_answer = claude.generate_answer(last_query, last_search_results)
        no_rag_answer = claude.generate_answer(last_query, None)
        
        return Div(
            H3("📊 RAG vs Default Comparison", cls="text-2xl font-bold mb-4 text-center"),
            
            # Side-by-side comparison
            Div(
                # RAG Answer (Left)
                Div(
                    H4("🤖 With RAG Context", cls="text-lg font-bold mb-3 text-green-700 text-center"),
                    Div(
                        render_markdown(rag_answer) if rag_answer else "Failed to generate RAG answer",
                        cls="prose prose-sm max-w-none bg-green-50 p-4 rounded border-l-4 border-green-400 leading-relaxed h-96 overflow-y-auto"
                    ),
                    P("✅ Answer generated using relevant documentation context", 
                      cls="text-xs text-green-600 italic mt-2 text-center"),
                    cls="w-1/2 pr-2"
                ),
                
                # No-RAG Answer (Right)
                Div(
                    H4("🧠 Default Claude", cls="text-lg font-bold mb-3 text-blue-700 text-center"),
                    Div(
                        render_markdown(no_rag_answer) if no_rag_answer else "Failed to generate default answer",
                        cls="prose prose-sm max-w-none bg-blue-50 p-4 rounded border-l-4 border-blue-400 leading-relaxed h-96 overflow-y-auto"
                    ),
                    P("ℹ️ Answer generated without any documentation context", 
                      cls="text-xs text-blue-600 italic mt-2 text-center"),
                    cls="w-1/2 pl-2"
                ),
                
                cls="flex gap-4"
            ),
            
            # Comparison insights
            Div(
                P("💡 Compare the responses to see how RAG improves accuracy and provides specific, context-aware answers.", 
                  cls="text-sm text-gray-600 italic text-center mt-4 p-3 bg-gray-50 rounded"),
                cls="mt-4"
            ),
            
            cls="mb-6 border rounded-lg p-6 bg-gradient-to-r from-green-50 via-white to-blue-50"
        )
        
    except Exception as e:
        return Div(
            P(f"❌ Error generating comparison: {str(e)}", 
              cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
            cls="mb-4"
        )

@app.post('/load-doc')
def load_doc(doc_id: str):
    """Load XML and chunks for selected document using HTMX"""
    if not doc_id:
        return Div("Please select a document", cls="text-gray-500 italic p-4")
    
    xml_content = db.get_document_xml(doc_id)
    chunks = db.get_document_chunks(doc_id)
    
    return Div(
        Div(
            H3("XML Content", cls="text-lg font-semibold mb-2"),
            Div(id="xml-viewer", style="height: 40vh; border: 1px solid #ccc; margin-bottom: 20px;"),
            Script(f"""
                setTimeout(() => {{
                    if (!monacoReady) {{
                        initMonacoOnce();
                        setTimeout(() => updateXmlContent({repr(xml_content)}), 200);
                    }} else {{
                        updateXmlContent({repr(xml_content)});
                    }}
                }}, 100);
            """)
        ),
        Div(
            H3(f"Chunks ({len(chunks)})", cls="text-lg font-semibold mb-2"),
            Div(
                *[Div(
                    Div(f"Level {chunk['section_level']}: {chunk['section_title']}", cls="font-semibold mb-2"),
                    Pre(chunk['content'], cls="bg-gray-100 p-3 rounded text-sm whitespace-pre-wrap"),
                    cls="mb-4 border-b pb-4"
                ) for chunk in chunks],
                cls="max-h-96 overflow-y-auto bg-gray-50 p-4 rounded"
            ) if chunks else P("No chunks found for this document.", cls="text-gray-500 italic")
        ),
        cls="block"  # Make sure it's visible
    )

@app.get('/generate-answer-streaming')
async def generate_answer_streaming():
    """Generate AI answer with streaming response using Server-Sent Events - ORIGINAL WORKING VERSION"""
    global last_search_results, last_query
    
    if not claude.is_available():
        return StreamingResponse(
            generate_error_stream("Claude API not available. Please check your ANTHROPIC_API_KEY."),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    if not last_search_results:
        return StreamingResponse(
            generate_error_stream("No search results available. Please perform a search first."),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    async def generate():
        try:
            yield "data: " + json.dumps({"type": "start", "content": ""}) + "\n\n"
            
            full_response = ""
            async for chunk in claude.generate_answer_streaming(last_query, last_search_results):
                full_response += chunk
                yield "data: " + json.dumps({"type": "chunk", "content": chunk}) + "\n\n"
                await asyncio.sleep(0.01)  # Small delay for smoother streaming
            
            # Send complete markdown content
            yield "data: " + json.dumps({"type": "complete", "content": full_response}) + "\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            yield "data: " + json.dumps({"type": "error", "content": f"Error generating answer: {str(e)}"}) + "\n\n"
    
    return StreamingResponse(
        generate(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache", 
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8"
        }
    )

async def generate_error_stream(error_msg: str):
    """Generate error stream"""
    yield "data: " + json.dumps({"type": "error", "content": error_msg}) + "\n\n"

@app.post('/generate-answer-streaming')
def generate_answer_streaming_post():
    """Non-streaming fallback for POST requests"""
    global last_search_results, last_query
    
    if not claude.is_available():
        return Div(
            P("❌ Claude API not available. Please check your ANTHROPIC_API_KEY in .env file.", 
              cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
            cls="mb-4"
        )
    
    if not last_search_results:
        return Div(
            P("❌ No search results available. Please perform a search first.", 
              cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
            cls="mb-4"
        )
    
    try:
        answer = claude.generate_answer(last_query, last_search_results)
        
        if answer:
            return Div(
                Div(
                    render_markdown(answer),
                    cls="prose max-w-none bg-green-50 p-4 rounded border-l-4 border-green-400 text-sm leading-relaxed"
                ),
                P("💡 This answer was generated using context from the search results above.", 
                  cls="text-xs text-gray-500 italic mt-3 border-t pt-3"),
                cls=""
            )
        else:
            return Div(
                P("❌ Failed to generate answer. Please try again.", 
                  cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
                cls="mb-4"
            )
    
    except Exception as e:
        return Div(
            P(f"❌ Error generating answer: {str(e)}", 
              cls="text-red-500 p-4 bg-red-50 rounded border-l-4 border-red-400"),
            cls="mb-4"
        )

# No-RAG Streaming Endpoint
@app.get('/generate-answer-no-rag-streaming')
async def generate_answer_no_rag_streaming():
    """Generate AI answer WITHOUT RAG context with streaming response using Server-Sent Events"""
    global last_query
    
    if not claude.is_available():
        return StreamingResponse(
            generate_error_stream("Claude API not available. Please check your ANTHROPIC_API_KEY."),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    if not last_query:
        return StreamingResponse(
            generate_error_stream("No query available. Please perform a search first."),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    async def generate():
        try:
            yield "data: " + json.dumps({"type": "start", "content": ""}) + "\n\n"
            
            full_response = ""
            # Generate answer WITHOUT RAG context (pass None instead of results)
            async for chunk in claude.generate_answer_streaming(last_query, None):
                full_response += chunk
                yield "data: " + json.dumps({"type": "chunk", "content": chunk}) + "\n\n"
                await asyncio.sleep(0.01)
            
            yield "data: " + json.dumps({"type": "complete", "content": full_response}) + "\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            yield "data: " + json.dumps({"type": "error", "content": f"Error generating answer: {str(e)}"}) + "\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

# HTMX Toggle and Utility Endpoints
@app.post('/toggle-viewer')
def toggle_viewer():
    """Toggle document viewer visibility"""
    docs = db.get_all_documents()
    
    # Return the content in hidden state (simulate toggle)
    return Div(
        Div(
            Select(
                Option("📋 Select a document to view...", value=""),
                *[Option(f"📄 {doc['title'] or doc['url'].split('/')[-1]}", value=doc['id']) 
                  for doc in docs],
                id="doc-selector",
                name="doc_id",
                hx_post="/load-doc",
                hx_target="#content-container",
                hx_trigger="change",
                hx_swap="innerHTML",
                cls="w-full p-3 border-2 border-gray-200 rounded-xl focus:border-blue-500 focus:outline-none transition-colors duration-200 text-gray-700 bg-white"
            ),
            cls="mb-6"
        ),
        Div(id="content-container", cls="hidden"),
        id="viewer-content",
        style="display: none;"  # Initially hidden after toggle
    )

@app.post('/toggle-urls')
def toggle_urls():
    """Toggle URLs list visibility"""
    from utils.batch import fasthtml_doc_urls
    
    # Return the URLs content in hidden state
    return Div(
        Div(
            H3(f"URLs to Process ({len(fasthtml_doc_urls)})", cls="text-lg font-semibold text-gray-800 mb-4"),
            Div(
                *[Div(
                    Span(f"{i+1}.", cls="text-gray-500 font-mono text-sm mr-3"),
                    Span(url.split('/')[-1] or url.split('/')[-2], cls="font-medium text-gray-800"),
                    Div(url, cls="text-xs text-gray-500 mt-1"),
                    cls="p-3 border-b border-gray-100 last:border-b-0 hover:bg-gray-50 transition-colors duration-150"
                ) for i, url in enumerate(fasthtml_doc_urls)],
                cls="bg-white rounded-lg border border-gray-200 max-h-60 overflow-y-auto"
            ),
            cls="mb-6"
        ),
        
        # Progress and Controls
        Div(
            ProgressDisplayModern(),
            StartButtonModern(),
            cls="space-y-4"
        ),
        
        id="urls-content",
        style="display: none;"  # Initially hidden after toggle
    )

@app.post('/toggle-log')
def toggle_log():
    """Toggle log content visibility"""
    return Div(
        Div(id="log-content", cls="mt-6 bg-gray-50 p-4 rounded max-h-96 overflow-y-auto"),
        Button("Clear Log", 
               hx_post="/clear-log", 
               hx_target="#log-content",
               hx_swap="innerHTML",
               cls="mt-2 bg-gray-500 text-white px-4 py-2 rounded"),
        id="log-content-wrapper",
        style="display: none;"  # Initially hidden after toggle
    )

@app.post('/clear-log')
def clear_log():
    """Clear log content"""
    return ""  # Return empty content to clear the log

@app.ws('/ws')
async def ws(msg: str, send):
    global batch_running
    
    if not batch_running:
        batch_running = True
        await send(Div(LogContainer(), id="log-section", style="display: block;", hx_swap_oob='true'))
        await send(StartButton(disabled=True, hx_swap_oob='true'))
        
        total = len(fasthtml_doc_urls)
        
        # --- FIX: Get initial counts ONCE before the loop ---
        doc_count = db.get_document_count()
        chunk_count = db.get_chunk_count()
        
        for i, url in enumerate(fasthtml_doc_urls):
            start_time = time.time()
            
            result = await asyncio.to_thread(process_single_url, db, url)
            
            end_time = time.time()
            
            progress = int(((i + 1) / total) * 100)
            current_text = f"Processing {url.split('/')[-1]}"
            if i + 1 == total:
                current_text = "Batch processing complete!"
            
            await send(ProgressDisplay(
                progress=progress, text=current_text, current=i+1, total=total, hx_swap_oob='true'
            ))
            
            if result["status"] == "cached": 
                message = "Skipped (cached)"
                status_cls = 'bg-yellow-100 text-yellow-800'
            elif result["status"] == "processed": 
                message = f"Processed in {end_time - start_time:.2f}s ({result.get('sections', 0)} sections)"
                status_cls = 'bg-green-100 text-green-800'
                # --- FIX: Update counts in memory for a fast UI response ---
                doc_count += 1
                chunk_count += result.get('sections', 0)
            else: 
                message = f"Error: {result['error']}"
                status_cls = 'bg-red-100 text-red-800'
            
            log_entry = Div(
                Div(url, cls="font-semibold"), 
                Div(message, cls="text-sm"), 
                cls=f"p-2 mb-2 rounded {status_cls}", 
                hx_swap_oob="afterbegin:#log-content"
            )
            await send(log_entry)
        
            # --- FIX: Send the in-memory stats, don't re-query the database ---
            await send(DatabaseStats(doc_count, chunk_count, hx_swap_oob='true'))

        # Refresh the XML document viewer (dropdown) with updated documents
        await send(DocumentViewerModern(hx_swap_oob='true'))

        batch_running = False
        await send(StartButton(disabled=False, hx_swap_oob='true'))

serve()